import argparse
from collections import defaultdict, deque
import csv
import json
import math
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np
import torch
from ultralytics import YOLO

DEVICE = 0 if torch.cuda.is_available() else "cpu"


# ---------------- settings ----------------

parser = argparse.ArgumentParser()
parser.add_argument("--event-id", default="event_1")
parser.add_argument("--camera", type=int, default=0)
parser.add_argument("--calibrate", action="store_true")
parser.add_argument("--setup-obstacles", action="store_true")
parser.add_argument("--clear-calibration", action="store_true")
parser.add_argument("--clear-obstacles", action="store_true")
parser.add_argument("--event-capacity", type=int, default=None, help="Operator-defined maximum event capacity")
parser.add_argument("--hide-spatial-overlay", action="store_true", help="Hide spatial floor/obstacle visual overlay")
parser.add_argument("--color", action="store_true", help="Display camera feed in full color instead of default surveillance grayscale")
args = parser.parse_args()

ROOT = os.path.dirname(os.path.abspath(__file__))

MODEL_PATH = os.path.join(ROOT, "yolo11s.pt")
CALIBRATION_FILE = os.path.join(ROOT, "spatial_calibration.json")
OBSTACLE_FILE = os.path.join(ROOT, "obstacles.json")
STATE_FILE = os.path.join(ROOT, "crowd_state.json")
ALERT_FILE = os.path.join(ROOT, "alert_history.csv")

EVENT_ID = args.event_id
CAMERA_INDEX = args.camera
CAMERA_NAME = "Camera 01 - Main Entrance"

# Change this only if your local FastAPI server uses another port.
BACKEND_URL = os.getenv("CROWD_BACKEND_URL", "http://127.0.0.1:8001")

STREAM_PORT = 8000

MODEL_CONFIDENCE = 0.25
IMAGE_SIZE = 640
INFERENCE_EVERY = 2

GRID_ROWS = 2
GRID_COLS = 2

PEOPLE_PER_M2 = 2.0

MOVEMENT_THRESHOLD = 3
FLOW_ALPHA = 0.20
RISK_ALPHA = 0.20

TREND_HISTORY_SIZE = 10

ALERT_CONFIRM_FRAMES = 30
ALERT_COOLDOWN = 10

STATE_INTERVAL = 1.0
BACKEND_INTERVAL = 1.0


# ---------------- small helpers ----------------

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return default


def json_numpy_serializer(obj):
    if isinstance(obj, (np.floating, np.float32, np.float64)):
        return float(obj)
    if isinstance(obj, (np.integer, np.int32, np.int64)):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return str(obj)


def save_json_safe(path, data):
    """Write state without stopping the AI if Windows temporarily locks the file."""
    temp_path = path + ".tmp"

    try:
        with open(temp_path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, default=json_numpy_serializer)

        try:
            os.replace(temp_path, path)
        except PermissionError:
            # Another process may have the JSON open.
            # Keep the AI running and try again on the next interval.
            try:
                os.remove(temp_path)
            except OSError:
                pass
            return False

        return True

    except OSError:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass
        return False


def polygon_area(points):
    points = np.asarray(points, dtype=np.float32)

    if len(points) < 3:
        return 0.0

    return abs(float(cv2.contourArea(points)))


def intersect_polygons(first, second):
    """Intersection for convex polygons."""
    first = np.asarray(first, dtype=np.float32)
    second = np.asarray(second, dtype=np.float32)

    if len(first) < 3 or len(second) < 3:
        return None

    try:
        area, result = cv2.intersectConvexConvex(first, second)

        if result is None or area <= 0:
            return None

        return result.reshape(-1, 2)

    except cv2.error:
        return None


# ---------------- calibration ----------------

calibration = load_json(CALIBRATION_FILE, None)
obstacles = load_json(OBSTACLE_FILE, [])

if args.clear_calibration:
    try:
        os.remove(CALIBRATION_FILE)
    except FileNotFoundError:
        pass

    print("Calibration removed.")
    raise SystemExit


if args.clear_obstacles:
    try:
        os.remove(OBSTACLE_FILE)
    except FileNotFoundError:
        pass

    print("Obstacles removed.")
    raise SystemExit


class SpatialIntelligence:
    """
    Automatic Floor Detection, Obstacle Detection, and Usable Area Estimation Engine.
    Features:
      1. Perspective-aware automatic floor detection from scene geometry and tracked foot points.
      2. Support for reusable metric scale calibration fallback (spatial_calibration.json).
      3. Automatic obstacle detection via YOLO furniture/object classes + manual obstacle integration.
      4. Pixel-accurate usable floor calculation: Usable = Floor - Obstacles.
      5. Zone-level and overall real-world floor, obstacle, and usable m² estimation.
      6. Obstacle-aware congestion and spatial risk analysis.
      7. Dynamic visual spatial overlays for demonstration.
    """

    def __init__(self, calibration_data=None, manual_obstacles=None):
        self.manual_calibration = calibration_data
        self.manual_obstacles = manual_obstacles or []
        self.auto_floor_polygon = None
        self.auto_floor_confidence = 0.50
        self.detected_obstacles = []
        self.obstacle_confidence = 0.85
        self.foot_points_history = []
        self.is_metric_calibrated = (
            calibration_data is not None
            and "homography" in calibration_data
            and float(calibration_data.get("real_width_m", 0)) > 0
            and float(calibration_data.get("real_height_m", 0)) > 0
        )
        self.show_spatial_overlay = not args.hide_spatial_overlay
        self.last_obstacle_scan = 0
        self.OBSTACLE_CLASSES = {
            24: "Backpack",
            25: "Umbrella",
            26: "Handbag",
            28: "Suitcase",
            56: "Chair",
            57: "Couch",
            58: "Plant",
            59: "Bed",
            60: "Table",
            61: "Fixture",
            62: "TV/Monitor",
            63: "Laptop",
            72: "Appliance",
            73: "Book",
        }

        # Intelligent Adaptive Floor State (No naive frame-counter lock)
        # Uses asymmetric EMA smoothing: expands quickly when new walkable floor is verified,
        # stabilizes rock-solid when confident, and adapts smoothly when scene changes.
        self.floor_pinned_manually = False
        self.pinned_floor_polygon = None
        self.smoothed_floor_polygon = None
        self._boundary_clarity = 0.50
        self._recent_areas = []
        self._wall_floor_boundary_y = None
        self._boundary_history = []

    @property
    def floor_locked(self):
        """Backward-compatible property: true if manually pinned or high-confidence settled."""
        return self.floor_pinned_manually or (self.auto_floor_confidence >= 0.88 and len(self.foot_points_history) >= 20)

    def update_foot_points(self, person_foot_points):
        """Track ground contact points of detected people over time with temporal decay."""
        for pt in person_foot_points:
            self.foot_points_history.append(pt)
        if len(self.foot_points_history) > 180:
            self.foot_points_history = self.foot_points_history[-180:]

    def _detect_wall_floor_boundary(self, frame):
        """
        Detects the baseboard / floor baseline (48%-62% height) where the vertical wall and door
        meet the horizontal ground plane. Ignores upper vertical walls, doors, and hanging objects.
        """
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Compute vertical gradient (Sobel Y)
        sobel_y = cv2.Sobel(blurred, cv2.CV_64F, 0, 1, ksize=5)
        abs_sobel = np.abs(sobel_y)

        # Search in the true baseboard / floor threshold range (48% to 65% frame height)
        search_top = int(h * 0.48)
        search_bot = int(h * 0.65)

        row_edge_strength = np.sum(abs_sobel[search_top:search_bot, :], axis=1)

        if len(row_edge_strength) == 0:
            return int(h * 0.54)

        peak_idx = int(np.argmax(row_edge_strength))
        peak_row = peak_idx + search_top
        max_edge = row_edge_strength[peak_idx]
        mean_edge = np.mean(row_edge_strength) + 1e-5

        clarity = float(np.clip((max_edge / mean_edge - 1.0) / 2.0, 0.2, 1.0))
        self._boundary_clarity = 0.85 * self._boundary_clarity + 0.15 * clarity

        # Smooth boundary over time
        self._boundary_history.append(peak_row)
        if len(self._boundary_history) > 20:
            self._boundary_history = self._boundary_history[-20:]
        smoothed_y = int(np.median(self._boundary_history))

        # Clamp strictly to realistic floor baseline (50% to 62% height)
        smoothed_y = int(np.clip(smoothed_y, int(h * 0.50), int(h * 0.62)))
        self._wall_floor_boundary_y = smoothed_y
        return smoothed_y

    def detect_floor(self, frame):
        """
        Identifies the horizontal floor plane starting at the furniture ground baseline (50-60% height).
        Completely ignores the vertical wall and vertical door above it.
        """
        if self.floor_pinned_manually and self.pinned_floor_polygon is not None:
            self.auto_floor_polygon = self.pinned_floor_polygon
            self.auto_floor_confidence = 0.98
            return self.auto_floor_polygon, self.auto_floor_confidence

        h, w = frame.shape[:2]
        if self.is_metric_calibrated:
            calib_pts = self.manual_calibration.get("image_points")
            if calib_pts and len(calib_pts) == 4:
                self.auto_floor_polygon = np.asarray(calib_pts, dtype=np.float32)
                self.auto_floor_confidence = 1.0
                return self.auto_floor_polygon, self.auto_floor_confidence

        # Wall-floor horizon safely placed at the room baseboard level (52%-60% height)
        horizon_y = self._detect_wall_floor_boundary(frame)

        # If obstacles (Bed, Table) exist, align floor horizon with the furniture top edge
        if self.detected_obstacles:
            obs_tops = [int(np.min(obs["points"][:, 1])) for obs in self.detected_obstacles]
            min_obs_top = min(obs_tops)
            # Floor starts around where furniture is placed (no higher than 48% height)
            top_y = int(np.clip(min(horizon_y, min_obs_top), int(h * 0.48), int(h * 0.60)))
        else:
            top_y = horizon_y

        bot_y = h - 2

        # If validated standing feet exist farther back, allow slight extension
        if len(self.foot_points_history) >= 4:
            pts = np.array(self.foot_points_history)
            min_y = np.percentile(pts[:, 1], 5)
            if min_y < top_y:
                top_y = max(int(h * 0.45), int(min_y - 10))
            self.auto_floor_confidence = float(np.clip(0.75 + 0.22 * self._boundary_clarity, 0.75, 0.96))
        else:
            self.auto_floor_confidence = float(np.clip(0.65 + 0.25 * self._boundary_clarity, 0.65, 0.90))

        target_polygon = np.asarray([
            [0, top_y],
            [w, top_y],
            [w, bot_y],
            [0, bot_y]
        ], dtype=np.float32)

        if self.smoothed_floor_polygon is None:
            self.smoothed_floor_polygon = target_polygon.copy()
        else:
            alpha = 0.04 if self.auto_floor_confidence > 0.80 else 0.08
            self.smoothed_floor_polygon = (
                self.smoothed_floor_polygon * (1.0 - alpha) + target_polygon * alpha
            )

        self.auto_floor_polygon = self.smoothed_floor_polygon
        return self.auto_floor_polygon, self.auto_floor_confidence

    def record_area_reading(self, total_floor_m2):
        """Track recent area readings for stability telemetry."""
        self._recent_areas.append(total_floor_m2)
        if len(self._recent_areas) > 60:
            self._recent_areas = self._recent_areas[-60:]

    def check_scene_change(self, current_person_count):
        """Dynamic scene monitoring."""
        pass

    def _lock_floor(self):
        """Manually pin the current floor polygon."""
        if self.auto_floor_polygon is not None:
            self.floor_pinned_manually = True
            self.pinned_floor_polygon = self.auto_floor_polygon.copy()
            self.auto_floor_confidence = 0.98

    def unlock_floor(self):
        """Unpin the floor polygon so intelligent continuous adaptation resumes."""
        self.floor_pinned_manually = False
        self.pinned_floor_polygon = None
        self.smoothed_floor_polygon = None
        self.foot_points_history.clear()
        self._boundary_history.clear()
        self._recent_areas.clear()

    def update_obstacles_from_yolo(self, yolo_result, frame):
        """Extract obstacles from YOLO detection with NMS suppression to eliminate duplicates."""
        raw_boxes = []
        conf_sum = 0.0

        if yolo_result is not None and yolo_result.boxes is not None:
            boxes = yolo_result.boxes.xyxy.cpu().numpy()
            clss = yolo_result.boxes.cls.cpu().numpy().astype(int)
            confs = yolo_result.boxes.conf.cpu().numpy()

            # Filter valid obstacle detections
            for box, cls_id, conf in zip(boxes, clss, confs):
                if cls_id in self.OBSTACLE_CLASSES and conf >= 0.15:
                    x1, y1, x2, y2 = map(int, box)
                    raw_boxes.append({
                        "cls_id": cls_id,
                        "name": self.OBSTACLE_CLASSES[cls_id],
                        "box": (x1, y1, x2, y2),
                        "conf": float(conf)
                    })

        # Non-Maximum Suppression (NMS) to merge/suppress duplicate boxes
        kept_obstacles = []
        raw_boxes.sort(key=lambda x: x["conf"], reverse=True)

        for item in raw_boxes:
            b1 = item["box"]
            duplicate = False
            for kept in kept_obstacles:
                b2 = kept["box"]
                # Compute Intersection over Union (IoU)
                ix1, iy1 = max(b1[0], b2[0]), max(b1[1], b2[1])
                ix2, iy2 = min(b1[2], b2[2]), min(b1[3], b2[3])
                inter_area = max(0, ix2 - ix1) * max(0, iy2 - iy1)
                area1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
                area2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
                iou = inter_area / max(1.0, area1 + area2 - inter_area)

                if iou > 0.35:
                    duplicate = True
                    break

            if not duplicate:
                kept_obstacles.append(item)

        detected = []
        for item in kept_obstacles:
            x1, y1, x2, y2 = item["box"]
            cls_id = item["cls_id"]
            if cls_id in (57, 59, 60):  # Bed, Couch, Table
                foot_y1 = int(y1 + 0.15 * (y2 - y1))
            else:
                foot_y1 = int(y1 + 0.45 * (y2 - y1))
            foot_y2 = y2
            pts = np.array(
                [
                    [x1, foot_y1],
                    [x2, foot_y1],
                    [x2, foot_y2],
                    [x1, foot_y2],
                ],
                dtype=np.float32
            )
            detected.append({
                "name": item["name"],
                "points": pts,
                "confidence": item["conf"],
            })
            conf_sum += item["conf"]

        # Include manual obstacles
        for obs in self.manual_obstacles:
            pts = np.asarray(obs.get("points", []), dtype=np.float32)
            if len(pts) >= 3:
                detected.append({
                    "name": obs.get("name", "Obstacle"),
                    "points": pts,
                    "confidence": 0.95,
                })
                conf_sum += 0.95

        self.detected_obstacles = detected
        self.obstacle_confidence = (conf_sum / len(detected)) if detected else 0.85

    def get_floor_points(self):
        if self.auto_floor_polygon is not None:
            return self.auto_floor_polygon
        if self.is_metric_calibrated:
            pts = self.manual_calibration.get("image_points")
            if pts:
                return np.asarray(pts, dtype=np.float32)
        return None

    def get_homography(self):
        if self.is_metric_calibrated and "homography" in self.manual_calibration:
            return np.asarray(self.manual_calibration["homography"], dtype=np.float32)
        return None

    def get_zone_spatial_metrics(self, zone_idx, width, height):
        """
        Calculates Floor Area, Obstacle Area, and Usable Area (in m²) for a specific zone
        using pixel-accurate masking and furniture metric anchors (Bed/Couch/Chairs).
        Also returns zone furniture seating capacity.
        """
        zone_width = width / GRID_COLS
        zone_height = height / GRID_ROWS
        col = zone_idx % GRID_COLS
        row = zone_idx // GRID_COLS
        x1 = int(col * zone_width)
        y1 = int(row * zone_height)
        x2 = int((col + 1) * zone_width)
        y2 = int((row + 1) * zone_height)

        floor_pts = self.get_floor_points()
        if floor_pts is None or len(floor_pts) < 3:
            return 4.0, 0.0, 4.0, 0.0, 0

        zone_mask = np.zeros((height, width), dtype=np.uint8)
        zone_mask[y1:y2, x1:x2] = 255

        floor_mask = np.zeros((height, width), dtype=np.uint8)
        cv2.fillPoly(floor_mask, [np.asarray(floor_pts, dtype=np.int32)], 255)

        obstacle_mask = np.zeros((height, width), dtype=np.uint8)
        zone_furniture_cap = 0
        bed_pixels = 0

        for obs in self.detected_obstacles:
            obs_pts_int = np.asarray(obs["points"], dtype=np.int32)
            if len(obs_pts_int) >= 3:
                cv2.fillPoly(obstacle_mask, [obs_pts_int], 255)
                obs_single_mask = np.zeros((height, width), dtype=np.uint8)
                cv2.fillPoly(obs_single_mask, [obs_pts_int], 255)
                overlap = cv2.countNonZero(cv2.bitwise_and(zone_mask, obs_single_mask))
                if overlap > 400:
                    name_lower = obs.get("name", "").lower()
                    if "bed" in name_lower:
                        zone_furniture_cap += 2
                        bed_pixels += cv2.contourArea(obs_pts_int)
                    elif "couch" in name_lower:
                        zone_furniture_cap += 2
                        bed_pixels += cv2.contourArea(obs_pts_int)
                    elif "chair" in name_lower:
                        zone_furniture_cap += 1
                    elif "table" in name_lower or "desk" in name_lower:
                        zone_furniture_cap += 1

        zone_floor_mask = cv2.bitwise_and(zone_mask, floor_mask)
        zone_usable_mask = cv2.bitwise_and(zone_floor_mask, cv2.bitwise_not(obstacle_mask))

        zone_floor_px = cv2.countNonZero(zone_floor_mask)
        zone_usable_px = cv2.countNonZero(zone_usable_mask)
        zone_obs_px = max(0, zone_floor_px - zone_usable_px)

        if zone_floor_px == 0:
            return 0.0, 0.0, 0.0, 0.0, zone_furniture_cap

        homography = self.get_homography()
        if homography is not None:
            zone_poly = np.asarray([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.float32)
            clipped_floor = intersect_polygons(zone_poly, floor_pts)
            if clipped_floor is not None and len(clipped_floor) >= 3:
                ground_floor = cv2.perspectiveTransform(clipped_floor.reshape(-1, 1, 2), homography).reshape(-1, 2)
                floor_m2 = polygon_area(ground_floor)
                obs_ratio = zone_obs_px / max(1, zone_floor_px)
                obs_m2 = floor_m2 * obs_ratio
                usable_m2 = max(0.0, floor_m2 - obs_m2)
            else:
                floor_m2, obs_m2, usable_m2, obs_ratio = 0.0, 0.0, 0.0, 0.0
        else:
            total_frame_px = width * height
            center_y = (y1 + y2) / 2.0
            perspective_weight = 1.0 / max(0.25, (center_y / height))

            if bed_pixels > 3000:
                # Bed metric anchor (~2.2 m²)
                scale_m2_per_px = 2.2 / max(1.0, bed_pixels)
                floor_m2 = max(0.2, round(zone_floor_px * scale_m2_per_px * 1.5, 2))
            else:
                floor_m2 = (zone_floor_px / (0.45 * total_frame_px)) * 14.0 * 0.25 * (1.0 / (perspective_weight ** 0.5))
                floor_m2 = max(0.2, round(floor_m2, 2))

            obs_ratio = zone_obs_px / max(1, zone_floor_px)
            obs_m2 = round(floor_m2 * obs_ratio, 2)
            usable_m2 = max(0.0, round(floor_m2 - obs_m2, 2))

        return float(floor_m2), float(obs_m2), float(usable_m2), float(obs_ratio), int(zone_furniture_cap)

    def draw_spatial_overlay(self, frame):
        """
        Renders visual spatial overlays:
        - Walkable floor areas (left of bed, right of bed, walkways) in translucent green with glowing outlines
        - Obstacles (Bed, Couch, Tables) in translucent red with red outlines
        - Wall/Floor horizon indicator line
        """
        if not self.show_spatial_overlay:
            return frame

        overlay = frame.copy()
        h, w = frame.shape[:2]

        floor_pts = self.get_floor_points()
        if floor_pts is not None and len(floor_pts) >= 3:
            pts_int = np.asarray(floor_pts, dtype=np.int32)

            # Create base floor mask
            floor_mask = np.zeros((h, w), dtype=np.uint8)
            cv2.fillPoly(floor_mask, [pts_int], 255)

            # Create obstacle mask
            obstacle_mask = np.zeros((h, w), dtype=np.uint8)
            for obs in self.detected_obstacles:
                obs_pts_int = np.asarray(obs["points"], dtype=np.int32)
                if len(obs_pts_int) >= 3:
                    cv2.fillPoly(obstacle_mask, [obs_pts_int], 255)

            # Usable walkable floor mask (all floor areas outside obstacles)
            usable_mask = cv2.bitwise_and(floor_mask, cv2.bitwise_not(obstacle_mask))

            # Draw usable floor regions in translucent vibrant green
            overlay[usable_mask > 0] = (
                overlay[usable_mask > 0] * 0.76 + np.array([0, 195, 85], dtype=np.uint8) * 0.24
            ).astype(np.uint8)

            # Draw obstacles in translucent red
            overlay[obstacle_mask > 0] = (
                overlay[obstacle_mask > 0] * 0.65 + np.array([0, 30, 220], dtype=np.uint8) * 0.35
            ).astype(np.uint8)

            # Find and draw clean contours for all usable floor islands (left of bed, right of bed, front)
            contours, _ = cv2.findContours(usable_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                if cv2.contourArea(cnt) > 300:
                    cv2.drawContours(overlay, [cnt], -1, (0, 255, 130), 2, cv2.LINE_AA)

            # Draw obstacle outlines and labels
            for obs in self.detected_obstacles:
                obs_pts_int = np.asarray(obs["points"], dtype=np.int32)
                if len(obs_pts_int) >= 3:
                    cv2.polylines(overlay, [obs_pts_int], True, (0, 60, 255), 2, cv2.LINE_AA)
                    cx = int(np.mean(obs_pts_int[:, 0]))
                    cy = int(np.mean(obs_pts_int[:, 1]))
                    draw_text(overlay, f"{obs['name']}", (cx - 20, cy), (255, 255, 255), 0.45, 1)

            # Wall/Floor boundary horizon line
            top_y = int(np.min(pts_int[:, 1]))
            cv2.line(overlay, (0, top_y), (w, top_y), (220, 210, 40), 1, cv2.LINE_AA)
            draw_text(overlay, "Wall/Floor Horizon", (10, max(18, top_y - 6)), (220, 210, 40), 0.35, 1)

        return overlay


spatial_engine = SpatialIntelligence(calibration, obstacles)


class TemporalCrowdIntelligence:
    """
    Temporal Crowd Intelligence & Forecasting Layer:
    - Maintains rolling temporal history (30s, 60s, 5-minute buffers).
    - Computes real-time crowd growth rate (people/min) and momentum trend.
    - Tracks ByteTrack track transitions across zones (incoming, outgoing, net_flow, concentration trend).
    - Evaluates usable-space vs crowd pressure dynamics over time.
    - Generates explainable 5-minute prototype crowd forecast.
    - Computes multi-factor Rush Forecast (LOW, MODERATE, ELEVATED, HIGH).
    """

    def __init__(self, history_len=180):
        self.history = deque(maxlen=history_len)  # (timestamp, people, usable_area, risk, zone_counts)
        self.track_prev_zones = {}  # track_id -> (zone_idx, timestamp)
        self.zone_transitions = defaultdict(lambda: {"incoming": 0, "outgoing": 0, "last_reset": time.time()})
        self.growth_rate = 0.0  # people / minute
        self.crowd_trend = "STABLE"  # "INCREASING", "DECREASING", "STABLE"
        self.rush_forecast = "LOW"  # "LOW", "MODERATE", "ELEVATED", "HIGH"
        self.rush_score = 0.0  # 0 to 100
        self.projected_people_5min = 0
        self.spatial_pressure = "NORMAL"  # "NORMAL", "INCREASING", "HIGH"
        self.dominant_flow_direction = "STATIONARY"
        self.total_net_flow = 0

    def update(self, current_people, usable_area, current_time, active_track_zones, current_risk=0.0, zone_counts=None):
        """
        Record instantaneous state and update temporal momentum, zone transitions,
        growth rate, and short-term forecasts.
        """
        if zone_counts is None:
            zone_counts = [0, 0, 0, 0]

        # 1. Update rolling history
        self.history.append((current_time, current_people, usable_area, current_risk, list(zone_counts)))

        # 2. Track zone-to-zone transitions
        for track_id, current_zone in active_track_zones.items():
            if track_id in self.track_prev_zones:
                prev_zone, prev_time = self.track_prev_zones[track_id]
                if prev_zone != current_zone:
                    # Person transitioned between zones
                    self.zone_transitions[current_zone]["incoming"] += 1
                    self.zone_transitions[prev_zone]["outgoing"] += 1
            self.track_prev_zones[track_id] = (current_zone, current_time)

        # Decay/clean stale track IDs inactive for > 15s
        stale_ids = [tid for tid, (_, t_seen) in self.track_prev_zones.items() if current_time - t_seen > 15.0]
        for tid in stale_ids:
            del self.track_prev_zones[tid]

        # Decay zone transition counters every 30s to keep flow metrics reactive and fresh
        for z in list(self.zone_transitions.keys()):
            if current_time - self.zone_transitions[z]["last_reset"] > 30.0:
                self.zone_transitions[z]["incoming"] = int(self.zone_transitions[z]["incoming"] * 0.5)
                self.zone_transitions[z]["outgoing"] = int(self.zone_transitions[z]["outgoing"] * 0.5)
                self.zone_transitions[z]["last_reset"] = current_time

        # 3. Calculate growth rate using a 30-45s rolling window
        if len(self.history) >= 2:
            t_now = self.history[-1][0]
            oldest_idx = 0
            for i, (t_past, _, _, _, _) in enumerate(self.history):
                if t_now - t_past <= 45.0:
                    oldest_idx = i
                    break

            t_start, p_start, u_start, r_start, _ = self.history[oldest_idx]
            dt = max(1.0, t_now - t_start)
            dp = current_people - p_start

            if dt >= 3.0:
                raw_growth_rate = (dp / dt) * 60.0  # people/min
                self.growth_rate = round(0.35 * raw_growth_rate + 0.65 * self.growth_rate, 2)
            else:
                self.growth_rate = 0.0

            # Determine crowd growth trend
            if self.growth_rate >= 1.5:
                self.crowd_trend = "INCREASING"
            elif self.growth_rate <= -1.5:
                self.crowd_trend = "DECREASING"
            else:
                self.crowd_trend = "STABLE"

            # Determine spatial pressure (usable area reducing while people increasing)
            du = usable_area - u_start
            if du < -0.8 and dp > 0:
                self.spatial_pressure = "HIGH"
            elif du < -0.3 or (dp > 1 and usable_area < 5.0):
                self.spatial_pressure = "INCREASING"
            else:
                self.spatial_pressure = "NORMAL"

        # 4. Explainable 5-minute Prototype Crowd Forecast
        delta_5min = self.growth_rate * 5.0
        if current_people <= 1 and self.growth_rate < 3.0:
            self.projected_people_5min = current_people
        else:
            self.projected_people_5min = max(0, int(round(current_people + delta_5min)))

        # 5. Multi-factor Rush Forecast Engine
        rush_pts = 0.0

        # Factor A: Crowd growth momentum
        if self.growth_rate >= 4.0:
            rush_pts += 30.0
        elif self.growth_rate >= 2.0:
            rush_pts += 20.0
        elif self.growth_rate >= 0.8:
            rush_pts += 10.0

        # Factor B: Zone concentration peak (max net flow across zones)
        max_net_flow = 0
        tot_net = 0
        for z in range(4):
            trans = self.zone_transitions[z]
            net = trans["incoming"] - trans["outgoing"]
            tot_net += abs(net)
            if net > max_net_flow:
                max_net_flow = net
        self.total_net_flow = tot_net

        if max_net_flow >= 5:
            rush_pts += 25.0
        elif max_net_flow >= 3:
            rush_pts += 15.0
        elif max_net_flow >= 1:
            rush_pts += 5.0

        # Factor C: Spatial pressure (people density vs usable area)
        density_val = (current_people / usable_area) if usable_area > 0 else 0.0
        if density_val >= 2.5 and current_people >= 3:
            rush_pts += 25.0
        elif density_val >= 1.5 and current_people >= 2:
            rush_pts += 15.0
        elif self.spatial_pressure == "HIGH":
            rush_pts += 10.0

        # Factor D: Current risk momentum
        if current_risk >= 70:
            rush_pts += 20.0
        elif current_risk >= 45:
            rush_pts += 10.0

        self.rush_score = min(100.0, max(0.0, rush_pts))

        if self.rush_score >= 60.0 and current_people >= 3:
            self.rush_forecast = "HIGH"
        elif self.rush_score >= 38.0 and current_people >= 2:
            self.rush_forecast = "ELEVATED"
        elif self.rush_score >= 18.0 and current_people >= 1:
            self.rush_forecast = "MODERATE"
        else:
            self.rush_forecast = "LOW"

    def get_zone_flow_metrics(self, zone_idx):
        """
        Return incoming, outgoing, net flow and concentration trend for a specific zone.
        """
        trans = self.zone_transitions[zone_idx]
        incoming = trans["incoming"]
        outgoing = trans["outgoing"]
        net_flow = incoming - outgoing

        if net_flow >= 2:
            concentration = "CONCENTRATION INCREASING"
        elif net_flow <= -2:
            concentration = "DISPERSING"
        else:
            concentration = "STABLE"

        return {
            "incoming": incoming,
            "outgoing": outgoing,
            "net_flow": net_flow,
            "concentration_trend": concentration,
        }


temporal_engine = TemporalCrowdIntelligence()


def get_calibration_points():
    return spatial_engine.get_floor_points()


def get_homography():
    return spatial_engine.get_homography()


def project_to_ground(points):
    homography = get_homography()

    if homography is None:
        return None

    points = np.asarray(points, dtype=np.float32)

    if len(points) < 1:
        return None

    return cv2.perspectiveTransform(
        points.reshape(-1, 1, 2),
        homography
    ).reshape(-1, 2)


def get_zone_polygon(zone, width, height):
    zone_width = width / GRID_COLS
    zone_height = height / GRID_ROWS

    col = zone % GRID_COLS
    row = zone // GRID_COLS

    x1 = col * zone_width
    y1 = row * zone_height
    x2 = (col + 1) * zone_width
    y2 = (row + 1) * zone_height

    return np.asarray(
        [
            [x1, y1],
            [x2, y1],
            [x2, y2],
            [x1, y2],
        ],
        dtype=np.float32
    )


def get_calibrated_zone(zone, width, height):
    floor = get_calibration_points()

    if floor is None:
        return None

    return intersect_polygons(
        get_zone_polygon(zone, width, height),
        floor
    )


def get_zone_area(zone, width, height):
    floor_m2, _, _, _ = spatial_engine.get_zone_spatial_metrics(zone, width, height)
    return floor_m2


def get_obstacle_area(zone, width, height):
    _, obs_m2, _, _ = spatial_engine.get_zone_spatial_metrics(zone, width, height)
    return obs_m2


def calibrate_floor():
    camera = cv2.VideoCapture(
        CAMERA_INDEX,
        cv2.CAP_DSHOW
    )

    if not camera.isOpened():
        raise RuntimeError("Camera could not be opened.")

    points = []

    def mouse_callback(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(points) < 4:
            points.append([x, y])

    cv2.namedWindow("Floor Calibration")
    cv2.setMouseCallback(
        "Floor Calibration",
        mouse_callback
    )

    print()
    print("Floor calibration")
    print("Click: top-left, top-right, bottom-right, bottom-left")
    print("ENTER = save")
    print("R = reset")
    print("ESC = cancel")

    while True:
        ok, frame = camera.read()

        if not ok:
            continue

        view = frame.copy()

        for index, point in enumerate(points):
            point = tuple(map(int, point))

            cv2.circle(
                view,
                point,
                7,
                (0, 255, 255),
                -1
            )

            cv2.putText(
                view,
                str(index + 1),
                point,
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2
            )

        if len(points) >= 2:
            cv2.polylines(
                view,
                [np.asarray(points, dtype=np.int32)],
                False,
                (0, 255, 255),
                2
            )

        cv2.putText(
            view,
            "Click 4 floor corners | ENTER save | R reset | ESC cancel",
            (20, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2
        )

        cv2.imshow(
            "Floor Calibration",
            view
        )

        key = cv2.waitKey(1) & 255

        if key == 27:
            break

        if key in (ord("r"), ord("R")):
            points.clear()

        if key == 13 and len(points) == 4:
            break

    camera.release()
    cv2.destroyWindow("Floor Calibration")

    if len(points) != 4:
        raise SystemExit("Calibration cancelled.")

    try:
        width = float(input("Real floor width (metres): "))
        height = float(input("Real floor height (metres): "))
    except ValueError:
        raise SystemExit("Invalid dimensions.")

    if width <= 0 or height <= 0:
        raise SystemExit("Dimensions must be greater than zero.")

    image_points = np.asarray(
        points,
        dtype=np.float32
    )

    real_points = np.asarray(
        [
            [0, 0],
            [width, 0],
            [width, height],
            [0, height],
        ],
        dtype=np.float32
    )

    homography = cv2.getPerspectiveTransform(
        image_points,
        real_points
    )

    save_json_safe(
        CALIBRATION_FILE,
        {
            "image_points": points,
            "real_width_m": width,
            "real_height_m": height,
            "homography": homography.tolist(),
        }
    )

    print(
        f"Saved floor: {width}m x {height}m "
        f"= {width * height:.2f}m2"
    )


if args.calibrate:
    calibrate_floor()
    raise SystemExit


def setup_obstacles():
    if calibration is None:
        raise SystemExit(
            "Calibrate the floor before adding obstacles."
        )

    camera = cv2.VideoCapture(
        CAMERA_INDEX,
        cv2.CAP_DSHOW
    )

    if not camera.isOpened():
        raise RuntimeError("Camera could not be opened.")

    ok, frame = camera.read()
    camera.release()

    if not ok:
        raise RuntimeError("Could not read camera.")

    current = []
    saved = []

    window = "Obstacle Setup"

    def mouse_callback(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(current) < 4:
            current.append([x, y])

    cv2.namedWindow(window)
    cv2.setMouseCallback(
        window,
        mouse_callback
    )

    print()
    print("Obstacle setup")
    print("Click 4 corners of an obstacle.")
    print("ENTER = add obstacle")
    print("S = save")
    print("R = reset current")
    print("ESC = cancel")

    while True:
        view = frame.copy()

        floor = get_calibration_points()

        if floor is not None:
            cv2.polylines(
                view,
                [floor.astype(np.int32)],
                True,
                (0, 165, 255),
                3
            )

        for obstacle in saved:
            cv2.polylines(
                view,
                [np.asarray(obstacle["points"], dtype=np.int32)],
                True,
                (255, 0, 255),
                2
            )

        if len(current) >= 2:
            cv2.polylines(
                view,
                [np.asarray(current, dtype=np.int32)],
                False,
                (0, 0, 255),
                3
            )

        for point in current:
            cv2.circle(
                view,
                tuple(point),
                6,
                (0, 0, 255),
                -1
            )

        cv2.putText(
            view,
            "4 corners | ENTER add | S save | R reset | ESC cancel",
            (15, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2
        )

        cv2.imshow(
            window,
            view
        )

        key = cv2.waitKey(30) & 255

        if key == 27:
            break

        if key in (ord("r"), ord("R")):
            current.clear()

        elif key == 13 and len(current) == 4:
            saved.append(
                {
                    "name": f"obstacle_{len(saved) + 1}",
                    "points": current.copy(),
                }
            )
            current.clear()

        elif key in (ord("s"), ord("S")):
            break

    cv2.destroyWindow(window)

    save_json_safe(
        OBSTACLE_FILE,
        saved
    )

    print(f"Saved {len(saved)} obstacles.")


if args.setup_obstacles:
    setup_obstacles()
    raise SystemExit


# ---------------- camera stream ----------------

latest_jpeg = None
jpeg_lock = threading.Lock()


class StreamHandler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(
                b"AI Crowd Intelligence stream is running. "
                b"Open /video_feed."
            )
            return

        if not self.path.startswith("/video_feed"):
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(200)

        self.send_header(
            "Content-Type",
            "multipart/x-mixed-replace; boundary=frame"
        )

        self.send_header(
            "Cache-Control",
            "no-cache, no-store, must-revalidate"
        )

        self.send_header(
            "Pragma",
            "no-cache"
        )

        self.send_header(
            "Access-Control-Allow-Origin",
            "*"
        )

        self.end_headers()

        try:
            while True:
                with jpeg_lock:
                    image = latest_jpeg

                if image is not None:
                    self.wfile.write(
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n"
                        + image
                        + b"\r\n"
                    )

                time.sleep(0.03)

        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format, *args):
        return


video_server = ThreadingHTTPServer(
    ("0.0.0.0", STREAM_PORT),
    StreamHandler
)

threading.Thread(
    target=video_server.serve_forever,
    daemon=True
).start()


# ---------------- camera capture thread ----------------

class CameraCapture:

    def __init__(self, source):
        self.source = source
        self.capture = None
        self.frame = None
        self.lock = threading.Lock()
        self.running = False

    def start(self):
        self.capture = cv2.VideoCapture(
            self.source,
            cv2.CAP_DSHOW
        )

        if not self.capture.isOpened():
            raise RuntimeError(
                "Could not open webcam."
            )

        self.capture.set(
            cv2.CAP_PROP_FRAME_WIDTH,
            640
        )

        self.capture.set(
            cv2.CAP_PROP_FRAME_HEIGHT,
            480
        )

        self.capture.set(
            cv2.CAP_PROP_BUFFERSIZE,
            1
        )

        self.running = True

        threading.Thread(
            target=self._read_loop,
            daemon=True
        ).start()

        return self

    def _read_loop(self):
        while self.running:
            ok, frame = self.capture.read()

            if not ok:
                time.sleep(0.01)
                continue

            # Mirror the video stream horizontally (natural mirror orientation)
            frame = cv2.flip(frame, 1)

            with self.lock:
                self.frame = frame

    def read(self):
        with self.lock:
            if self.frame is None:
                return None

            return self.frame.copy()

    def stop(self):
        self.running = False

        if self.capture is not None:
            self.capture.release()


camera = CameraCapture(
    CAMERA_INDEX
).start()


# ---------------- backend uploader ----------------

class BackendUploader:

    def __init__(self, url):
        self.url = url
        self.latest_state = None
        self.lock = threading.Lock()
        self.running = True
        self.connected = False

    def update(self, state):
        with self.lock:
            self.latest_state = state

    def start(self):
        threading.Thread(
            target=self._loop,
            daemon=True
        ).start()

    def _loop(self):
        while self.running:
            with self.lock:
                state = self.latest_state

            if state is not None:
                self.send(state)

            time.sleep(BACKEND_INTERVAL)

    def send(self, state):
        try:
            data = json.dumps(state).encode("utf-8")

            request = urllib.request.Request(
                self.url + "/api/crowd-state",
                data=data,
                headers={
                    "Content-Type": "application/json"
                },
                method="POST"
            )

            with urllib.request.urlopen(
                request,
                timeout=2
            ):
                pass

            if not self.connected:
                print("Backend connection established.")

            self.connected = True

        except Exception:
            if self.connected:
                print("Backend connection lost.")

            self.connected = False

    def stop(self):
        self.running = False


backend = BackendUploader(
    BACKEND_URL
)

backend.start()


# ---------------- tracking ----------------

model = YOLO(MODEL_PATH)

tracks = {}

demographics_cache = {}


def _classify_face(person_crop, box_h, box_w):
    """
    Face-based gender classification for close-up scenarios.
    Detects mustache / beard / stubble via dark-texture analysis
    in the lower face region.
    Returns (gender, age, confidence).
    """
    crop_h, crop_w = person_crop.shape[:2]

    try:
        gray = cv2.cvtColor(
            person_crop,
            cv2.COLOR_BGR2GRAY
        )
        hsv = cv2.cvtColor(
            person_crop,
            cv2.COLOR_BGR2HSV
        )
    except Exception:
        return "Unknown", "Adult", 0.1

    score = 0.0

    # Face center horizontal band.
    fx1 = int(crop_w * 0.20)
    fx2 = int(crop_w * 0.80)

    # Lower face (mouth / mustache / chin).
    jaw_y1 = int(crop_h * 0.45)
    jaw_y2 = int(crop_h * 0.65)

    jaw_gray = gray[jaw_y1:jaw_y2, fx1:fx2]
    jaw_hsv = hsv[jaw_y1:jaw_y2, fx1:fx2]

    if jaw_gray.size == 0:
        return "Unknown", "Adult", 0.1

    # Signal 1: facial hair = dark + low saturation patches.
    dark_mask = (
        (jaw_gray < 80)
        & (jaw_hsv[:, :, 1] < 60)
    )
    dark_ratio = (
        float(np.sum(dark_mask))
        / max(1, jaw_gray.size)
    )

    if dark_ratio > 0.08:
        score -= 2.5
    elif dark_ratio > 0.04:
        score -= 1.5

    # Signal 2: jaw edge density vs forehead (facial hair
    # creates much more texture than smooth forehead).
    jaw_edges = cv2.Canny(jaw_gray, 20, 80)
    jaw_edge_d = float(np.mean(jaw_edges)) / 255.0

    forehead_y1 = int(crop_h * 0.15)
    forehead_y2 = int(crop_h * 0.30)
    forehead = gray[forehead_y1:forehead_y2, fx1:fx2]

    if forehead.size > 0:
        fh_edges = cv2.Canny(forehead, 20, 80)
        fh_edge_d = float(np.mean(fh_edges)) / 255.0
    else:
        fh_edge_d = jaw_edge_d

    if (
        jaw_edge_d > fh_edge_d * 1.5
        and jaw_edge_d > 0.05
    ):
        score -= 1.5

    # Signal 3: jaw brightness vs overall face brightness.
    # Stubble / shadow makes lower face darker.
    face_region = gray[
        int(crop_h * 0.15):int(crop_h * 0.65),
        fx1:fx2
    ]

    if face_region.size > 0:
        jaw_bright = float(np.mean(jaw_gray))
        face_bright = float(np.mean(face_region))

        if jaw_bright < face_bright * 0.85:
            score -= 1.0

    # Signal 4: lower face edge concentration.
    # Smooth lower face (no facial hair) leans female.
    if jaw_edge_d < 0.03 and dark_ratio < 0.02:
        score += 1.5

    # Classify.
    if score <= -1.5:
        gender = "Male"
    elif score >= 1.5:
        gender = "Female"
    else:
        gender = "Unknown"

    confidence = min(1.0, abs(score) / 4.0)

    return gender, "Adult", confidence


def estimate_demographics(person_crop, bbox, speed=0.0):
    """
    Multi-signal gender and age classifier.
    Combines body silhouette, color analysis, texture features,
    and calibrated real-world height when available.
    Returns (gender, age, confidence).
    """
    x1, y1, x2, y2 = bbox
    box_w = max(1, x2 - x1)
    box_h = max(1, y2 - y1)
    aspect = box_h / float(box_w)

    # Scores: positive = female / senior, negative = male / child.
    g_score = 0.0
    a_score = 0.0

    if (
        person_crop is None
        or person_crop.size == 0
        or box_h < 15
        or box_w < 10
    ):
        return "Unknown", "Adult", 0.1

    # Too close to camera for body-based classification.
    # Switch to face-based analysis instead (mustache, jaw,
    # facial texture).
    if aspect < 1.5 and box_h > 200:
        return _classify_face(person_crop, box_h, box_w)

    crop_h, crop_w = person_crop.shape[:2]

    if crop_h < 10 or crop_w < 6:
        return "Unknown", "Adult", 0.1

    try:
        hsv = cv2.cvtColor(
            person_crop,
            cv2.COLOR_BGR2HSV
        )
        gray = cv2.cvtColor(
            person_crop,
            cv2.COLOR_BGR2GRAY
        )
    except Exception:
        return "Unknown", "Adult", 0.1

    # Body region boundaries.
    head_end = max(2, int(crop_h * 0.18))
    upper_end = max(
        head_end + 2,
        int(crop_h * 0.42)
    )
    lower_end = max(
        upper_end + 2,
        int(crop_h * 0.60)
    )

    head_gray = gray[:head_end, :]
    upper_hsv = hsv[head_end:upper_end, :]
    lower_hsv = hsv[upper_end:lower_end, :]
    upper_gray = gray[head_end:upper_end, :]
    lower_gray = gray[upper_end:lower_end, :]

    # ---- Gender signal 1: shoulder vs hip silhouette ----

    shoulder_y = min(
        crop_h - 1,
        int(crop_h * 0.24)
    )
    hip_y = min(
        crop_h - 1,
        int(crop_h * 0.54)
    )

    s_strip = gray[
        max(0, shoulder_y - 2):shoulder_y + 3, :
    ]
    h_strip = gray[
        max(0, hip_y - 2):hip_y + 3, :
    ]

    s_fill = (
        float(np.sum(s_strip > 30))
        / max(1.0, float(s_strip.size))
    )
    h_fill = (
        float(np.sum(h_strip > 30))
        / max(1.0, float(h_strip.size))
    )

    if h_fill > 0.15:
        shr = s_fill / h_fill
        if shr > 1.15:
            g_score -= 1.5
        elif shr < 0.92:
            g_score += 1.5

    # ---- Gender signal 2: upper body color saturation ----

    upper_sat = (
        float(np.mean(upper_hsv[:, :, 1]))
        if upper_hsv.size > 0
        else 50.0
    )

    if upper_sat > 82:
        g_score += 1.3
    elif upper_sat < 42:
        g_score -= 0.9

    # ---- Gender signal 3: hue diversity in upper body ----

    if upper_hsv.size > 0:
        hue_std = float(
            np.std(upper_hsv[:, :, 0])
        )
        if hue_std > 38:
            g_score += 1.0
        elif hue_std < 14:
            g_score -= 0.7

    # ---- Gender signal 4: head edge complexity (hair) ----

    if head_gray.size > 20:
        head_edges = cv2.Canny(
            head_gray, 30, 100
        )
        edge_density = (
            float(np.mean(head_edges)) / 255.0
        )
        if edge_density > 0.14:
            g_score += 0.9

    # ---- Gender signal 5: lower body silhouette ----

    if lower_gray.size > 20:
        col_fill = np.sum(
            lower_gray > 25, axis=1
        ).astype(float)

        if len(col_fill) > 4:
            half = len(col_fill) // 2
            top_w = float(np.mean(col_fill[:half]))
            bot_w = float(np.mean(col_fill[half:]))

            if top_w > 5 and bot_w / top_w > 1.35:
                g_score += 1.2

    # ---- Gender signal 6: full outfit color ----

    if lower_hsv.size > 0:
        lower_sat = float(
            np.mean(lower_hsv[:, :, 1])
        )
        if lower_sat > 75 and upper_sat > 70:
            g_score += 0.7

    # ---- Age signal 7: calibrated real-world height ----

    homography = get_homography()

    if homography is not None:
        try:
            cx = (x1 + x2) / 2.0

            head_pt = np.asarray(
                [[[cx, float(y1)]]],
                dtype=np.float32
            )
            foot_pt = np.asarray(
                [[[cx, float(y2)]]],
                dtype=np.float32
            )

            hg = cv2.perspectiveTransform(
                head_pt, homography
            )
            fg = cv2.perspectiveTransform(
                foot_pt, homography
            )

            real_h = math.hypot(
                hg[0, 0, 0] - fg[0, 0, 0],
                hg[0, 0, 1] - fg[0, 0, 1]
            )

            if real_h > 0.3:
                if real_h < 1.20:
                    a_score -= 4.5
                elif real_h < 1.40:
                    a_score -= 2.5
                elif real_h > 1.75:
                    a_score += 0.3

        except Exception:
            pass

    # ---- Age signal 8: head-to-body proportion ----

    head_ratio = head_end / float(crop_h)

    if head_ratio > 0.26:
        a_score -= 1.5

    # ---- Age signal 9: aspect ratio + pixel height ----

    if aspect < 2.0 and box_h < 110:
        a_score -= 2.5
    elif aspect < 2.15 and box_h < 90:
        a_score -= 1.8

    # ---- Age signal 10: movement speed ----

    if speed > 14:
        a_score -= 0.6
    elif speed < 1.2 and box_h > 90:
        a_score += 1.2

    # ---- Age signal 11: head brightness / hair color ----

    if head_gray.size > 10:
        hb = float(np.mean(head_gray))
        hs = float(np.std(head_gray))

        if hb > 145 and hs < 28:
            a_score += 2.2
        elif hb > 130 and hs < 34:
            a_score += 1.0

    # ---- Age signal 12: clothing contrast + speed ----

    if upper_gray.size > 10:
        upper_contrast = float(
            np.std(upper_gray)
        )
        if upper_contrast < 25 and speed < 2.0:
            a_score += 0.6

    # ---- Final classification ----

    confidence = min(
        1.0,
        max(
            abs(g_score),
            abs(a_score)
        ) / 5.0
    )

    if g_score >= 1.5:
        gender = "Female"
    elif g_score <= -1.0:
        gender = "Male"
    else:
        gender = "Unknown"

    if a_score <= -2.5:
        age = "Child"
    elif a_score >= 3.0:
        age = "Senior Citizen"
    else:
        age = "Adult"

    return gender, age, confidence


def get_person_demographics(
    track_id,
    person_crop,
    bbox,
    speed=0.0
):
    current_time = time.time()

    if track_id not in demographics_cache:
        g, a, conf = estimate_demographics(
            person_crop, bbox, speed
        )
        demographics_cache[track_id] = {
            "gender": g,
            "age": a,
            "gender_scores": {g: conf},
            "age_scores": {a: conf},
            "last_updated": current_time,
            "updates": 1,
        }
    else:
        entry = demographics_cache[track_id]

        if (
            entry["updates"] < 12
            or (current_time - entry["last_updated"] > 1.5)
        ):
            g, a, conf = estimate_demographics(
                person_crop, bbox, speed
            )

            entry["gender_scores"][g] = (
                entry["gender_scores"].get(g, 0)
                + conf
            )
            entry["age_scores"][a] = (
                entry["age_scores"].get(a, 0)
                + conf
            )

            entry["gender"] = max(
                entry["gender_scores"],
                key=entry["gender_scores"].get
            )
            entry["age"] = max(
                entry["age_scores"],
                key=entry["age_scores"].get
            )

            entry["last_updated"] = current_time
            entry["updates"] += 1

    return (
        demographics_cache[track_id]["gender"],
        demographics_cache[track_id]["age"]
    )


def prune_demographics(active_ids):
    if len(demographics_cache) > 200:
        active_set = set(active_ids)
        to_del = [
            tid for tid in demographics_cache
            if tid not in active_set
        ]
        for tid in to_del:
            del demographics_cache[tid]


zone_history = [
    []
    for _ in range(GRID_ROWS * GRID_COLS)
]

flow_vectors = [
    np.zeros(2, dtype=np.float32)
    for _ in range(GRID_ROWS * GRID_COLS)
]

risk_values = [
    0.0
    for _ in range(GRID_ROWS * GRID_COLS)
]

high_risk_frames = 0
last_alert_time = 0

last_state_save = 0


def get_density(count):
    if count <= 5:
        return "LOW"

    if count <= 10:
        return "MEDIUM"

    if count <= 15:
        return "HIGH"

    return "CRITICAL"


def get_flow(vector):
    x = float(vector[0])
    y = float(vector[1])

    speed = math.hypot(x, y)

    if speed < 0.8:
        return "STATIONARY"

    if abs(x) >= abs(y):
        return "RIGHT" if x > 0 else "LEFT"

    return "DOWN" if y > 0 else "UP"


def calculate_risk(
    people,
    capacity,
    occupancy,
    density,
    flow_state,
    trend,
    obstacle_ratio=0.0,
    net_flow=0,
    temporal_pressure=0.0
):
    if people <= 0:
        return 0.0

    # 1 person in a room/zone is always completely SAFE (0-10 max)
    if people == 1:
        return 5.0

    # Normal occupancy <= 100% is safe/moderate; only significant crowding over capacity raises risk
    if occupancy <= 100.0:
        occupancy_score = (occupancy / 100.0) * 25.0
    else:
        over_cap = min(100.0, occupancy - 100.0)
        occupancy_score = 25.0 + (over_cap / 100.0) * 35.0

    density_score = {
        "LOW": 0.0,
        "MEDIUM": 5.0,
        "HIGH": 12.0,
        "CRITICAL": 20.0,
    }.get(density, 0.0)

    flow_score = {
        "SMOOTH": 0.0,
        "UNSTABLE": 6.0,
        "CONGESTED": 12.0,
    }.get(flow_state, 0.0)

    trend_score = 5.0 if trend == "INCREASING" else 0.0

    # Obstacle bottleneck factor: only applies if multiple people are squeezed around tight obstacles
    obstacle_penalty = 0.0
    if obstacle_ratio > 0.35 and people >= 3:
        obstacle_penalty = min(10.0, (obstacle_ratio - 0.35) * 20.0)

    # Temporal concentration bonus: only if 3+ people are converging on this zone
    concentration_penalty = 0.0
    if net_flow >= 2 and people >= 3:
        concentration_penalty = min(8.0, float(net_flow) * 2.0)

    score = (
        occupancy_score
        + density_score
        + flow_score
        + trend_score
        + obstacle_penalty
        + concentration_penalty
        + min(8.0, float(temporal_pressure))
    )

    # 1 or 2 people in a residential/office room cannot exceed SAFE risk
    if people <= 2:
        score = min(20.0, score)

    return min(100.0, score)


def risk_level(score):
    if score <= 25:
        return "SAFE"

    if score <= 50:
        return "MODERATE"

    if score <= 75:
        return "HIGH"

    return "CRITICAL"


def draw_text(
    image,
    text,
    position,
    color=(255, 255, 255),
    size=0.55,
    thickness=1
):
    cv2.putText(
        image,
        text,
        position,
        cv2.FONT_HERSHEY_SIMPLEX,
        size,
        color,
        thickness,
        cv2.LINE_AA
    )


def save_alert(
    score,
    level,
    people,
    occupancy
):
    file_exists = os.path.exists(ALERT_FILE)

    try:
        with open(
            ALERT_FILE,
            "a",
            newline="",
            encoding="utf-8"
        ) as file:
            writer = csv.writer(file)

            if not file_exists:
                writer.writerow(
                    [
                        "time",
                        "risk",
                        "level",
                        "people",
                        "occupancy",
                    ]
                )

            writer.writerow(
                [
                    time.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    score,
                    level,
                    people,
                    occupancy,
                ]
            )

    except OSError:
        pass


# ---------------- main loop ----------------

WINDOW_NAME = "AI Crowd Intelligence"

cv2.namedWindow(
    WINDOW_NAME,
    cv2.WINDOW_NORMAL
)

cv2.resizeWindow(
    WINDOW_NAME,
    1280,
    720
)

fullscreen = False

frame_number = 0
last_result = None
last_obs_result = None

print()
print("==========================================")
print(" AI CROWD INTELLIGENCE ENGINE")
print("==========================================")
print(f"Event:      {EVENT_ID}")
print(f"Camera:     {CAMERA_NAME}")
print(f"Backend:    {BACKEND_URL}")
print(f"Stream:     http://localhost:{STREAM_PORT}/video_feed")

if spatial_engine.is_metric_calibrated:
    cal_w = calibration.get("real_width_m", 0)
    cal_h = calibration.get("real_height_m", 0)
    print(f"Floor:      Calibrated ({cal_w}m x {cal_h}m = {cal_w * cal_h:.2f}m2)")
else:
    print("Floor:      Auto-Detect Mode (Perspective geometry scale)")

print(f"Manual Obs: {len(obstacles)}")
print("G = toggle grayscale/color | L = pin/unpin floor | F = fullscreen | O = spatial overlay | Q / ESC = exit")
print("==========================================")
print()

running = True
grayscale_mode = not args.color

try:
    while running:

        frame = camera.read()

        if frame is None:
            time.sleep(0.005)
            continue

        frame_number += 1

        height, width = frame.shape[:2]
        color_frame = frame.copy()

        # Surveillance Grayscale Mode: High-contrast monochrome video with vivid color overlays
        if grayscale_mode:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

        # Automatic Floor Detection & Geometry update
        spatial_engine.detect_floor(frame)

        # Periodic Obstacle Detection via YOLO furniture/object classes (throttled for performance)
        if last_obs_result is None or frame_number % 20 == 0:
            try:
                last_obs_result = model.predict(
                    color_frame,
                    classes=[24, 25, 26, 28, 56, 57, 58, 59, 60, 61, 62, 63, 72, 73],
                    conf=0.15,
                    imgsz=IMAGE_SIZE,
                    device=DEVICE,
                    verbose=False
                )[0]
                spatial_engine.update_obstacles_from_yolo(last_obs_result, frame)
            except Exception:
                pass

        # Run YOLO Person Detection every second frame.
        # ByteTrack keeps track IDs between inference frames.
        if (
            last_result is None
            or frame_number % INFERENCE_EVERY == 0
        ):
            last_result = model.track(
                color_frame,
                persist=True,
                classes=[0],
                conf=MODEL_CONFIDENCE,
                imgsz=IMAGE_SIZE,
                tracker="bytetrack.yaml",
                device=DEVICE,
                verbose=False
            )[0]

        result = last_result

        zone_counts = [
            0
            for _ in range(GRID_ROWS * GRID_COLS)
        ]

        zone_speeds = [
            []
            for _ in range(GRID_ROWS * GRID_COLS)
        ]

        people_data = []
        current_foot_points = []

        if (
            result is not None
            and result.boxes is not None
            and result.boxes.id is not None
        ):
            boxes = (
                result.boxes.xyxy
                .cpu()
                .numpy()
            )

            ids = (
                result.boxes.id
                .cpu()
                .numpy()
                .astype(int)
            )

            for box, track_id in zip(
                boxes,
                ids
            ):
                x1, y1, x2, y2 = map(
                    int,
                    box
                )

                center_x = int(
                    (x1 + x2) / 2
                )

                center_y = int(
                    (y1 + y2) / 2
                )

                head_point = (
                    center_x,
                    y1
                )

                body_point = (
                    center_x,
                    int((y1 + y2) / 2)
                )

                foot_point = (
                    center_x,
                    y2
                )
                box_h = y2 - y1
                box_w = max(1, x2 - x1)
                # Only add as ground contact foot point if person is standing full-body (not sitting on a bed/chair or a close-up head)
                if (box_h / box_w >= 1.30 and box_h >= height * 0.22) or (y2 >= height * 0.88 and box_h >= height * 0.35):
                    current_foot_points.append([center_x, y2])

                col = min(
                    GRID_COLS - 1,
                    max(
                        0,
                        int(
                            center_x
                            / (width / GRID_COLS)
                        )
                    )
                )

                row = min(
                    GRID_ROWS - 1,
                    max(
                        0,
                        int(
                            center_y
                            / (height / GRID_ROWS)
                        )
                    )
                )

                zone = (
                    row * GRID_COLS
                    + col
                )

                zone_counts[zone] += 1

                previous = tracks.get(
                    int(track_id)
                )

                if previous is None:
                    dx = 0.0
                    dy = 0.0
                else:
                    dx = center_x - previous[0]
                    dy = center_y - previous[1]

                tracks[int(track_id)] = (
                    center_x,
                    center_y
                )

                speed = math.hypot(
                    dx,
                    dy
                )

                if speed < MOVEMENT_THRESHOLD:
                    dx = 0.0
                    dy = 0.0

                flow_vectors[zone] = (
                    FLOW_ALPHA
                    * np.asarray(
                        [dx, dy],
                        dtype=np.float32
                    )
                    + (1.0 - FLOW_ALPHA)
                    * flow_vectors[zone]
                )

                zone_speeds[zone].append(
                    speed
                )

                # Approximate lower-body footprint.
                foot_width = max(
                    4,
                    int((x2 - x1) * 0.45)
                )

                foot_height = max(
                    4,
                    int((y2 - y1) * 0.18)
                )

                fx1 = max(
                    0,
                    center_x - foot_width // 2
                )

                fx2 = min(
                    width - 1,
                    center_x + foot_width // 2
                )

                fy1 = max(
                    0,
                    y2 - foot_height
                )

                fy2 = min(
                    height - 1,
                    y2
                )

                footprint_pixels = max(
                    0,
                    (fx2 - fx1)
                    * (fy2 - fy1)
                )

                zone_polygon = get_zone_polygon(
                    zone,
                    width,
                    height
                )

                zone_area_pixels = int(
                    polygon_area(zone_polygon)
                )

                occupied_percent = (
                    footprint_pixels
                    / zone_area_pixels
                    * 100
                    if zone_area_pixels > 0
                    else 0
                )

                crop_y1 = max(0, y1)
                crop_y2 = min(height, y2)
                crop_x1 = max(0, x1)
                crop_x2 = min(width, x2)
                person_crop = (
                    frame[crop_y1:crop_y2, crop_x1:crop_x2]
                    if (crop_y2 > crop_y1 and crop_x2 > crop_x1)
                    else None
                )

                person_gender, person_age = get_person_demographics(
                    int(track_id),
                    person_crop,
                    (x1, y1, x2, y2),
                    speed
                )

                people_data.append(
                    {
                        "track_id": int(track_id),
                        "head_point": list(head_point),
                        "body_point": list(body_point),
                        "foot_point": list(foot_point),
                        "footprint_pixels": footprint_pixels,
                        "occupied_footprint_pixels": footprint_pixels,
                        "zone_area_pixels": zone_area_pixels,
                        "spatial_occupancy_percent": round(
                            occupied_percent,
                            2
                        ),
                        "zone": zone,
                        "age": person_age,
                        "gender": person_gender,
                    }
                )

                # Person box and points (clean display without individual demographic labels on camera feed).
                cv2.rectangle(
                    frame,
                    (x1, y1),
                    (x2, y2),
                    (0, 255, 0),
                    2
                )

                cv2.circle(
                    frame,
                    head_point,
                    5,
                    (255, 0, 255),
                    -1
                )

                cv2.circle(
                    frame,
                    foot_point,
                    4,
                    (0, 0, 255),
                    -1
                )

                draw_text(
                    frame,
                    f"ID: {track_id}",
                    (
                        x1,
                        max(20, y1 - 8)
                    ),
                    (0, 255, 0),
                    0.5,
                    2
                )

            prune_demographics(ids)

        if current_foot_points:
            spatial_engine.update_foot_points(current_foot_points)

        total_people = sum(zone_counts)
        active_track_zones = {p["id"]: p["zone"] for p in people_data if "id" in p}
        current_time = time.time()

        # Preliminary spatial estimates for temporal engine
        est_floor = sum(spatial_engine.get_zone_spatial_metrics(z, width, height)[0] for z in range(GRID_ROWS * GRID_COLS))
        est_obs = sum(spatial_engine.get_zone_spatial_metrics(z, width, height)[1] for z in range(GRID_ROWS * GRID_COLS))
        est_usable = max(0.0, est_floor - est_obs)

        # Update Temporal Crowd Intelligence & Forecasting Layer
        temporal_engine.update(
            current_people=total_people,
            usable_area=est_usable,
            current_time=current_time,
            active_track_zones=active_track_zones,
            current_risk=0.0,
            zone_counts=zone_counts
        )

        zones = []
        total_risk = 0.0

        for zone in range(
            GRID_ROWS * GRID_COLS
        ):
            count = zone_counts[zone]

            history = zone_history[zone]

            history.append(count)

            if len(history) > TREND_HISTORY_SIZE:
                history.pop(0)

            change = (
                history[-1] - history[0]
                if len(history) >= 2
                else 0
            )

            if change > 2:
                trend = "INCREASING"
            elif change < -2:
                trend = "DECREASING"
            else:
                trend = "STABLE"

            floor_area, obstacle_area, usable_area, obstacle_ratio, zone_furniture_cap = (
                spatial_engine.get_zone_spatial_metrics(zone, width, height)
            )

            if args.event_capacity is not None:
                # Operator-defined maximum event capacity distributed across zones
                capacity = max(1, int(round(args.event_capacity / (GRID_ROWS * GRID_COLS))))
            else:
                # Zone capacity: Walkable floor capacity + Furniture seating capacity (Bed/Couch/Chairs)
                floor_cap = int(math.ceil(usable_area * 1.5)) if usable_area > 0.3 else 0
                capacity = max(1 if (usable_area > 0.3 or zone_furniture_cap > 0) else 0, floor_cap + zone_furniture_cap)

            occupancy = (
                count
                / capacity
                * 100
                if capacity > 0
                else 0.0
            )

            flow = get_flow(
                flow_vectors[zone]
            )

            average_speed = (
                float(
                    np.mean(
                        zone_speeds[zone]
                    )
                )
                if zone_speeds[zone]
                else 0.0
            )

            speed_variation = (
                float(
                    np.std(
                        zone_speeds[zone]
                    )
                )
                if len(zone_speeds[zone]) > 1
                else 0.0
            )

            # Flow state: only mark CONGESTED if multiple people exceed capacity
            if (
                capacity > 0
                and count > capacity
                and count >= 2
            ):
                flow_state = "CONGESTED"

            elif speed_variation > 8:
                flow_state = "UNSTABLE"

            else:
                flow_state = "SMOOTH"

            density = get_density(count)

            # Temporal flow and concentration trend per zone
            flow_info = temporal_engine.get_zone_flow_metrics(zone)
            incoming = flow_info["incoming"]
            outgoing = flow_info["outgoing"]
            net_flow = flow_info["net_flow"]
            concentration_trend = flow_info["concentration_trend"]

            temporal_pressure = 4.0 if temporal_engine.spatial_pressure == "HIGH" else (2.0 if temporal_engine.spatial_pressure == "INCREASING" else 0.0)

            raw_risk = calculate_risk(
                count,
                capacity,
                occupancy,
                density,
                flow_state,
                trend,
                obstacle_ratio=obstacle_ratio,
                net_flow=net_flow,
                temporal_pressure=temporal_pressure
            )

            risk_values[zone] = (
                RISK_ALPHA * raw_risk
                + (1.0 - RISK_ALPHA)
                * risk_values[zone]
            )

            zone_risk = round(
                risk_values[zone]
            )

            total_risk = max(
                total_risk,
                zone_risk
            )

            zone_males = sum(1 for p in people_data if p["zone"] == zone and p["gender"] == "Male")
            zone_females = sum(1 for p in people_data if p["zone"] == zone and p["gender"] == "Female")
            zone_gender_unknown = sum(1 for p in people_data if p["zone"] == zone and p["gender"] == "Unknown")
            zone_children = sum(1 for p in people_data if p["zone"] == zone and p["age"] == "Child")
            zone_adults = sum(1 for p in people_data if p["zone"] == zone and p["age"] == "Adult")
            zone_seniors = sum(1 for p in people_data if p["zone"] == zone and p["age"] == "Senior Citizen")

            zones.append(
                {
                    "zone": zone,
                    "people": count,
                    "floor_area_m2": round(floor_area, 2),
                    "area_m2": round(floor_area, 2),
                    "obstacle_area_m2": round(
                        obstacle_area,
                        2
                    ),
                    "usable_area_m2": round(
                        usable_area,
                        2
                    ),
                    "obstacle_ratio": round(obstacle_ratio, 2),
                    "capacity": capacity,
                    "occupancy_percent": round(
                        occupancy,
                        1
                    ),
                    "people_per_m2": round(
                        count / usable_area,
                        2
                    ) if usable_area > 0 else 0,
                    "density": density,
                    "density_pm2": round(
                        count / usable_area,
                        2
                    ) if usable_area > 0 else 0.0,
                    "flow": flow,
                    "dominant_direction": flow,
                    "flow_speed_pixels": round(
                        average_speed,
                        2
                    ),
                    "flow_variation": round(
                        speed_variation,
                        2
                    ),
                    "flow_state": flow_state,
                    "trend": trend,
                    "incoming": incoming,
                    "outgoing": outgoing,
                    "net_flow": net_flow,
                    "concentration_trend": concentration_trend,
                    "risk": zone_risk,
                    "risk_level": risk_level(zone_risk),
                    "gender_distribution": {
                        "male": zone_males,
                        "female": zone_females,
                        "unknown": zone_gender_unknown,
                    },
                    "age_distribution": {
                        "child": zone_children,
                        "adult": zone_adults,
                        "senior": zone_seniors,
                    },
                }
            )

        total_people = sum(zone_counts)

        total_males = sum(1 for p in people_data if p["gender"] == "Male")
        total_females = sum(1 for p in people_data if p["gender"] == "Female")
        total_gender_unknown = sum(1 for p in people_data if p["gender"] == "Unknown")
        total_children = sum(1 for p in people_data if p["age"] == "Child")
        total_adults = sum(1 for p in people_data if p["age"] == "Adult")
        total_seniors = sum(1 for p in people_data if p["age"] == "Senior Citizen")

        total_floor_area = sum(
            zone["floor_area_m2"]
            for zone in zones
        )

        total_obstacle_area = sum(
            zone["obstacle_area_m2"]
            for zone in zones
        )

        total_usable_area = max(
            0.0,
            total_floor_area - total_obstacle_area
        )

        # Feed total floor area into stabilization tracker for auto-lock.
        spatial_engine.record_area_reading(total_floor_area)

        # Check if scene has changed enough to auto-unlock floor.
        spatial_engine.check_scene_change(total_people)

        total_capacity = sum(
            zone["capacity"]
            for zone in zones
        )

        total_occupancy = (
            total_people
            / total_capacity
            * 100
            if total_capacity > 0
            else 0.0
        )

        overall_level = risk_level(
            total_risk
        )

        # Identify highest risk zone
        highest_risk_zone_idx = 0
        highest_risk_score = 0
        for z_data in zones:
            if z_data["risk"] > highest_risk_score:
                highest_risk_score = z_data["risk"]
                highest_risk_zone_idx = z_data["zone"]

        # Alert only after sustained critical risk or elevated rush build-up.
        rush_alert_trigger = (temporal_engine.rush_forecast in ("ELEVATED", "HIGH") and total_people >= 3)
        if total_risk >= 76 or rush_alert_trigger:
            high_risk_frames += 1
        else:
            high_risk_frames = 0

        alert = False

        if (
            high_risk_frames
            >= ALERT_CONFIRM_FRAMES
            and current_time - last_alert_time
            >= ALERT_COOLDOWN
        ):
            alert = True
            last_alert_time = current_time

            save_alert(
                total_risk,
                overall_level,
                total_people,
                total_occupancy
            )

        spatial_confidence_label = (
            "PINNED" if spatial_engine.floor_pinned_manually
            else (
                "CALIBRATED" if spatial_engine.is_metric_calibrated
                else ("HIGH" if spatial_engine.auto_floor_confidence >= 0.85 else ("MEDIUM" if spatial_engine.auto_floor_confidence >= 0.70 else "LEARNING"))
            )
        )

        dominant_flow_overall = "STATIONARY"
        if zones:
            flow_counts = defaultdict(int)
            for z in zones:
                if z.get("flow") and z["flow"] != "STATIONARY":
                    flow_counts[z["flow"]] += 1
            if flow_counts:
                dominant_flow_overall = max(flow_counts, key=flow_counts.get)

        state = {
            "event_id": EVENT_ID,
            "camera_name": CAMERA_NAME,
            "timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),
            "total_people": total_people,
            "overall_risk": int(total_risk),
            "overall_risk_level": overall_level,
            "highest_risk_zone": highest_risk_zone_idx,
            "highest_risk_score": highest_risk_score,
            "highest_risk_level": risk_level(highest_risk_score),
            "alert": "CROWD PRESSURE / RISK ALERT" if alert else None,
            "gender_summary": {
                "male": total_males,
                "female": total_females,
                "unknown": total_gender_unknown,
                "male_percent": round((total_males / total_people * 100), 1) if total_people > 0 else 0.0,
                "female_percent": round((total_females / total_people * 100), 1) if total_people > 0 else 0.0,
                "unknown_percent": round((total_gender_unknown / total_people * 100), 1) if total_people > 0 else 0.0,
            },
            "age_summary": {
                "child": total_children,
                "adult": total_adults,
                "senior": total_seniors,
                "child_percent": round((total_children / total_people * 100), 1) if total_people > 0 else 0.0,
                "adult_percent": round((total_adults / total_people * 100), 1) if total_people > 0 else 0.0,
                "senior_percent": round((total_seniors / total_people * 100), 1) if total_people > 0 else 0.0,
            },
            "spatial": {
                "floor_detected": spatial_engine.get_floor_points() is not None,
                "floor_locked": spatial_engine.floor_locked,
                "floor_area_m2": round(total_floor_area, 2),
                "obstacle_area_m2": round(total_obstacle_area, 2),
                "usable_area_m2": round(total_usable_area, 2),
                "floor_detection_confidence": round(spatial_engine.auto_floor_confidence, 2),
                "obstacle_detection_confidence": round(spatial_engine.obstacle_confidence, 2),
                "spatial_confidence": spatial_confidence_label,
                "is_metric_calibrated": spatial_engine.is_metric_calibrated,
                "scale_mode": "calibrated" if spatial_engine.is_metric_calibrated else "auto_estimated",
                "detected_obstacles_count": len(spatial_engine.detected_obstacles),
            },
            "crowd": {
                "total_people": total_people,
                "density": round(total_people / total_usable_area, 2) if total_usable_area > 0 else 0.0,
                "density_pm2": round(total_people / total_usable_area, 2) if total_usable_area > 0 else 0.0,
                "occupancy_percent": round(total_occupancy, 1),
                "trend": temporal_engine.crowd_trend,
                "growth_rate": temporal_engine.growth_rate,
                "spatial_pressure": temporal_engine.spatial_pressure,
            },
            "flow": {
                "dominant_direction": dominant_flow_overall,
                "net_flow": temporal_engine.total_net_flow,
            },
            "temporal": {
                "trend": temporal_engine.crowd_trend,
                "growth_rate": temporal_engine.growth_rate,
                "growth_rate_per_min": temporal_engine.growth_rate,
                "spatial_pressure": temporal_engine.spatial_pressure,
            },
            "forecast": {
                "projected_people_5min": temporal_engine.projected_people_5min,
                "rush_forecast": temporal_engine.rush_forecast,
                "rush_score": round(temporal_engine.rush_score, 1),
                "label": "Prototype Forecast",
            },
            "risk": {
                "score": int(total_risk),
                "level": overall_level,
            },
            "total_area_m2": round(
                total_floor_area,
                2
            ),
            "floor_area_m2": round(
                total_floor_area,
                2
            ),
            "obstacle_area_m2": round(
                total_obstacle_area,
                2
            ),
            "usable_area_m2": round(
                total_usable_area,
                2
            ),
            "capacity": total_capacity,
            "occupancy_percent": round(
                total_occupancy,
                1
            ),
            "people_per_m2": round(
                total_people / total_usable_area,
                2
            ) if total_usable_area > 0 else 0,
            "zones": zones,
            "people": people_data,
            "calibration": {
                "enabled": spatial_engine.is_metric_calibrated,
                "width_m": (
                    calibration.get("real_width_m")
                    if calibration else None
                ),
                "height_m": (
                    calibration.get("real_height_m")
                    if calibration else None
                ),
            },
            "obstacles": len(spatial_engine.detected_obstacles),
        }

        # Save state once per second, not once per frame.
        if (
            current_time - last_state_save
            >= STATE_INTERVAL
        ):
            save_json_safe(
                STATE_FILE,
                state
            )

            backend.update(state)

            last_state_save = current_time

        # ---------------- camera overlay ----------------

        # Render visual spatial debugging overlays (translucent green walkable floor, red obstacles)
        frame = spatial_engine.draw_spatial_overlay(frame)

        # 2x2 Zone grid division lines
        cv2.line(
            frame,
            (width // 2, 0),
            (width // 2, height),
            (255, 255, 255),
            1
        )

        cv2.line(
            frame,
            (0, height // 2),
            (width, height // 2),
            (255, 255, 255),
            1
        )

        # Update local MJPEG stream.
        ok, jpeg = cv2.imencode(
            ".jpg",
            frame,
            [
                cv2.IMWRITE_JPEG_QUALITY,
                65
            ]
        )

        if ok:
            with jpeg_lock:
                latest_jpeg = jpeg.tobytes()

        # ---------------- structured dashboard ----------------

        display_width = 1280
        display_video_width = 900
        side_width = 380
        bottom_height = 130

        scale = (
            display_video_width
            / width
        )

        display_video_height = int(
            height * scale
        )

        camera_view = cv2.resize(
            frame,
            (
                display_video_width,
                display_video_height
            ),
            interpolation=cv2.INTER_AREA
        )

        dashboard = np.full(
            (
                display_video_height
                + bottom_height,
                display_width,
                3
            ),
            (238, 242, 245),
            dtype=np.uint8
        )

        dashboard[
            :display_video_height,
            :display_video_width
        ] = camera_view

        side = np.full(
            (
                display_video_height,
                side_width,
                3
            ),
            (245, 247, 249),
            dtype=np.uint8
        )

        draw_text(
            side,
            "LIVE CROWD & SPATIAL DATA",
            (18, 26),
            (30, 40, 50),
            0.60,
            2
        )

        if spatial_engine.floor_locked:
            scale_tag = "FLOOR LOCKED"
        elif spatial_engine.is_metric_calibrated:
            scale_tag = "Calibrated"
        else:
            scale_tag = f"Auto Floor ({int(spatial_engine.auto_floor_confidence * 100)}%)"
        draw_text(
            side,
            f"Event: {EVENT_ID} | {scale_tag}",
            (18, 48),
            (90, 105, 120),
            0.38,
            1
        )

        card_height = (
            display_video_height - 62
        ) // 4

        for zone, data in enumerate(zones):

            top = 58 + zone * card_height
            bottom = top + card_height - 6

            cv2.rectangle(
                side,
                (10, top),
                (side_width - 10, bottom),
                (255, 255, 255),
                -1
            )

            cv2.rectangle(
                side,
                (10, top),
                (side_width - 10, bottom),
                (215, 220, 225),
                1
            )

            draw_text(
                side,
                f"ZONE {zone + 1}",
                (20, top + 20),
                (30, 40, 50),
                0.50,
                2
            )

            draw_text(
                side,
                f"People: {data['people']} (Net: {data['net_flow']:+d})",
                (20, top + 42),
                (50, 60, 70),
                0.41,
                1
            )

            draw_text(
                side,
                f"Usable: {data['usable_area_m2']:.1f}m2",
                (200, top + 42),
                (0, 140, 70),
                0.40,
                1
            )

            draw_text(
                side,
                f"Floor: {data['floor_area_m2']:.1f}m2 | Obs: {data['obstacle_area_m2']:.1f}m2",
                (20, top + 63),
                (100, 110, 120),
                0.37,
                1
            )

            draw_text(
                side,
                f"Cap: {data['capacity']} | Occ: {data['occupancy_percent']:.1f}% | Den: {data['density_pm2']:.1f}p/m2",
                (20, top + 84),
                (0, 120, 190),
                0.37,
                1
            )

            draw_text(
                side,
                f"Flow: {data['flow']} | {data['concentration_trend'][:14]} | Risk: {data['risk']}",
                (20, top + 104),
                (70, 80, 95),
                0.36,
                1
            )

            draw_text(
                side,
                f"M:{data['gender_distribution']['male']} F:{data['gender_distribution']['female']} | C:{data['age_distribution']['child']} A:{data['age_distribution']['adult']} S:{data['age_distribution']['senior']}",
                (20, top + 124),
                (60, 100, 140),
                0.33,
                1
            )

        dashboard[
            :display_video_height,
            display_video_width:
        ] = side

        # ---------------- overall section ----------------

        bottom = np.full(
            (
                bottom_height,
                display_width,
                3
            ),
            (232, 237, 241),
            dtype=np.uint8
        )

        cv2.line(
            bottom,
            (0, 0),
            (display_width, 0),
            (200, 205, 210),
            2
        )

        draw_text(
            bottom,
            "OVERALL CROWD & SPATIAL INTELLIGENCE",
            (20, 26),
            (25, 35, 45),
            0.56,
            2
        )

        summary = [
            ("PEOPLE", str(total_people)),
            ("USABLE AREA", f"{total_usable_area:.1f} m2"),
            ("GROWTH RATE", f"{temporal_engine.growth_rate:+.1f}/min ({temporal_engine.crowd_trend})"),
            ("5-MIN FORECAST", f"~{temporal_engine.projected_people_5min} (Proto)"),
            ("RUSH FORECAST", f"{temporal_engine.rush_forecast}"),
            ("OVERALL RISK", f"{int(total_risk)} ({overall_level})"),
        ]

        summary_width = (display_width - 40) // len(summary)

        for index, (label, value) in enumerate(summary):

            x = 20 + index * summary_width

            draw_text(
                bottom,
                label,
                (x, 52),
                (100, 110, 120),
                0.35,
                1
            )

            color = (35, 145, 80)

            if "RISK" in label or "RUSH" in label:
                if total_risk > 75 or "HIGH" in value:
                    color = (40, 40, 210)
                elif total_risk > 50 or "ELEVATED" in value:
                    color = (0, 120, 220)
                elif total_risk > 25 or "MODERATE" in value:
                    color = (0, 145, 210)

            draw_text(
                bottom,
                value,
                (x, 82),
                color,
                0.46 if len(value) > 13 else 0.52,
                2
            )

        floor_status_str = "PINNED" if spatial_engine.floor_pinned_manually else f"{int(spatial_engine.auto_floor_confidence * 100)}% Conf"
        draw_text(
            bottom,
            f"Camera: {CAMERA_NAME} | Floor: {spatial_confidence_label} ({floor_status_str}) | Spatial Pressure: {temporal_engine.spatial_pressure}",
            (20, 114),
            (0, 140, 70) if spatial_engine.auto_floor_confidence >= 0.80 else (100, 110, 120),
            0.34,
            1
        )

        draw_text(
            bottom,
            "G: Gray/Color   L: Pin/Unpin   F: Fullscreen   O: Overlay   Q / ESC: Exit",
            (display_width - 440, 114),
            (100, 110, 120),
            0.34,
            1
        )

        dashboard[
            display_video_height:
            display_video_height + bottom_height,
            :
        ] = bottom

        cv2.imshow(
            WINDOW_NAME,
            dashboard
        )

        key = cv2.waitKey(1) & 255

        if key in (
            27,
            ord("q"),
            ord("Q")
        ):
            running = False

        elif key in (
            ord("g"),
            ord("G")
        ):
            grayscale_mode = not grayscale_mode
            print(f"Grayscale Mode: {'ENABLED' if grayscale_mode else 'DISABLED'}")

        elif key in (
            ord("l"),
            ord("L")
        ):
            if spatial_engine.floor_pinned_manually:
                spatial_engine.unlock_floor()
                print("Floor UNPINNED — continuous adaptive intelligence active.")
            else:
                spatial_engine._lock_floor()
                print("Floor PINNED manually — current polygon held.")

        elif key in (
            ord("o"),
            ord("O")
        ):
            spatial_engine.show_spatial_overlay = not spatial_engine.show_spatial_overlay

        elif key in (
            ord("f"),
            ord("F")
        ):
            fullscreen = not fullscreen

            if fullscreen:
                cv2.setWindowProperty(
                    WINDOW_NAME,
                    cv2.WND_PROP_FULLSCREEN,
                    cv2.WINDOW_FULLSCREEN
                )
            else:
                cv2.setWindowProperty(
                    WINDOW_NAME,
                    cv2.WND_PROP_FULLSCREEN,
                    cv2.WINDOW_NORMAL
                )

                cv2.resizeWindow(
                    WINDOW_NAME,
                    1280,
                    720
                )

finally:
    camera.stop()
    backend.stop()

    try:
        video_server.shutdown()
    except Exception:
        pass

    cv2.destroyAllWindows()

print("AI Crowd Intelligence stopped.")
