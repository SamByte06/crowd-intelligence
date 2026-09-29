import argparse
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
from ultralytics import YOLO


# ---------------- settings ----------------

parser = argparse.ArgumentParser()
parser.add_argument("--event-id", default="event_1")
parser.add_argument("--camera", type=int, default=0)
parser.add_argument("--calibrate", action="store_true")
parser.add_argument("--setup-obstacles", action="store_true")
parser.add_argument("--clear-calibration", action="store_true")
parser.add_argument("--clear-obstacles", action="store_true")
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

MODEL_CONFIDENCE = 0.30
IMAGE_SIZE = 416
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


def save_json_safe(path, data):
    """Write state without stopping the AI if Windows temporarily locks the file."""
    temp_path = path + ".tmp"

    try:
        with open(temp_path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)

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


def get_calibration_points():
    if calibration is None:
        return None

    points = calibration.get("image_points")

    if not points or len(points) != 4:
        return None

    return np.asarray(points, dtype=np.float32)


def get_homography():
    if calibration is None:
        return None

    # Newer calibration files already contain this.
    if "homography" in calibration:
        return np.asarray(
            calibration["homography"],
            dtype=np.float32
        )

    # Older calibration files can be upgraded automatically.
    image_points = get_calibration_points()

    if image_points is None:
        return None

    width = float(calibration.get("real_width_m", 0))
    height = float(calibration.get("real_height_m", 0))

    if width <= 0 or height <= 0:
        return None

    real_points = np.asarray(
        [
            [0, 0],
            [width, 0],
            [width, height],
            [0, height],
        ],
        dtype=np.float32
    )

    return cv2.getPerspectiveTransform(
        image_points,
        real_points
    )


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
    image_zone = get_calibrated_zone(
        zone,
        width,
        height
    )

    if image_zone is None:
        return 0.0

    ground_zone = project_to_ground(image_zone)

    if ground_zone is None:
        return 0.0

    return polygon_area(ground_zone)


def get_obstacle_area(zone, width, height):
    image_zone = get_calibrated_zone(
        zone,
        width,
        height
    )

    floor = get_calibration_points()

    if image_zone is None or floor is None:
        return 0.0

    total = 0.0

    for obstacle in obstacles:
        points = np.asarray(
            obstacle.get("points", []),
            dtype=np.float32
        )

        clipped_to_floor = intersect_polygons(
            points,
            floor
        )

        if clipped_to_floor is None:
            continue

        clipped_to_zone = intersect_polygons(
            clipped_to_floor,
            image_zone
        )

        if clipped_to_zone is None:
            continue

        ground = project_to_ground(clipped_to_zone)

        if ground is not None:
            total += polygon_area(ground)

    return total


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

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                b"AI Crowd Intelligence stream is running. "
                b"Open /video_feed."
            )
            return

        if self.path != "/video_feed":
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
    trend
):
    if people <= 0:
        return 0.0

    # Occupancy contributes most, but cannot alone force HIGH risk.
    occupancy_score = min(
        60.0,
        occupancy * 0.60
    )

    density_score = {
        "LOW": 0.0,
        "MEDIUM": 8.0,
        "HIGH": 16.0,
        "CRITICAL": 25.0,
    }[density]

    flow_score = {
        "SMOOTH": 0.0,
        "UNSTABLE": 8.0,
        "CONGESTED": 15.0,
    }[flow_state]

    trend_score = 7.0 if trend == "INCREASING" else 0.0

    score = (
        occupancy_score
        + density_score
        + flow_score
        + trend_score
    )

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

print()
print("==========================================")
print(" AI CROWD INTELLIGENCE ENGINE")
print("==========================================")
print(f"Event:      {EVENT_ID}")
print(f"Camera:     {CAMERA_NAME}")
print(f"Backend:    {BACKEND_URL}")
print(f"Stream:     http://localhost:{STREAM_PORT}/video_feed")

if calibration is not None:
    width = calibration.get("real_width_m", 0)
    height = calibration.get("real_height_m", 0)

    print(
        f"Floor:      {width}m x {height}m "
        f"= {width * height:.2f}m2"
    )
else:
    print("Floor:      not calibrated")

print(f"Obstacles:  {len(obstacles)}")
print("F = fullscreen")
print("Q / ESC = exit")
print("==========================================")
print()

running = True

try:
    while running:

        frame = camera.read()

        if frame is None:
            time.sleep(0.005)
            continue

        frame_number += 1

        height, width = frame.shape[:2]

        # Run YOLO every second frame.
        # ByteTrack keeps track IDs between inference frames.
        if (
            last_result is None
            or frame_number % INFERENCE_EVERY == 0
        ):
            last_result = model.track(
                frame,
                persist=True,
                classes=[0],
                conf=MODEL_CONFIDENCE,
                imgsz=IMAGE_SIZE,
                tracker="bytetrack.yaml",
                device=0,
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
                        "age": "not_estimated",
                        "gender": "not_estimated",
                    }
                )

                # Person box and points.
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

            area = get_zone_area(
                zone,
                width,
                height
            )

            obstacle_area = get_obstacle_area(
                zone,
                width,
                height
            )

            usable_area = max(
                0.0,
                area - obstacle_area
            )

            capacity = (
                int(
                    math.floor(
                        usable_area
                        * PEOPLE_PER_M2
                    )
                )
                if usable_area > 0
                else 0
            )

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

            if (
                capacity > 0
                and count >= capacity
            ):
                flow_state = "CONGESTED"

            elif speed_variation > 8:
                flow_state = "UNSTABLE"

            else:
                flow_state = "SMOOTH"

            density = get_density(count)

            raw_risk = calculate_risk(
                count,
                capacity,
                occupancy,
                density,
                flow_state,
                trend
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

            zones.append(
                {
                    "zone": zone,
                    "people": count,
                    "area_m2": round(area, 2),
                    "obstacle_area_m2": round(
                        obstacle_area,
                        2
                    ),
                    "usable_area_m2": round(
                        usable_area,
                        2
                    ),
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
                    "flow": flow,
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
                    "risk": zone_risk,
                }
            )

        total_people = sum(zone_counts)

        total_area = sum(
            zone["area_m2"]
            for zone in zones
        )

        total_obstacle_area = sum(
            zone["obstacle_area_m2"]
            for zone in zones
        )

        total_usable_area = max(
            0.0,
            total_area - total_obstacle_area
        )

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

        # Alert only after sustained critical risk.
        if total_risk >= 76:
            high_risk_frames += 1
        else:
            high_risk_frames = 0

        current_time = time.time()

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

        state = {
            "event_id": EVENT_ID,
            "camera_name": CAMERA_NAME,
            "timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),
            "total_people": total_people,
            "overall_risk": int(total_risk),
            "overall_risk_level": overall_level,
            "alert": alert,
            "total_area_m2": round(
                total_area,
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
                "enabled": calibration is not None,
                "width_m": (
                    calibration.get("real_width_m")
                    if calibration else None
                ),
                "height_m": (
                    calibration.get("real_height_m")
                    if calibration else None
                ),
            },
            "obstacles": len(obstacles),
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

        floor = get_calibration_points()

        if floor is not None:
            cv2.polylines(
                frame,
                [floor.astype(np.int32)],
                True,
                (0, 165, 255),
                2
            )

        for obstacle in obstacles:
            points = np.asarray(
                obstacle.get("points", []),
                dtype=np.int32
            )

            if len(points) >= 3:
                cv2.polylines(
                    frame,
                    [points],
                    True,
                    (255, 0, 255),
                    2
                )

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
            "LIVE CROWD DATA",
            (18, 28),
            (30, 40, 50),
            0.65,
            2
        )

        draw_text(
            side,
            f"Event: {EVENT_ID}",
            (18, 52),
            (100, 110, 120),
            0.42,
            1
        )

        card_height = (
            display_video_height - 68
        ) // 4

        for zone, data in enumerate(zones):

            top = 62 + zone * card_height
            bottom = top + card_height - 7

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
                (20, top + 23),
                (30, 40, 50),
                0.52,
                2
            )

            draw_text(
                side,
                f"People: {data['people']}",
                (20, top + 47),
                (50, 60, 70),
                0.43,
                1
            )

            draw_text(
                side,
                f"Area: {data['area_m2']:.1f} m2",
                (170, top + 47),
                (0, 130, 190),
                0.40,
                1
            )

            draw_text(
                side,
                f"Usable: {data['usable_area_m2']:.1f} m2",
                (20, top + 70),
                (0, 130, 190),
                0.40,
                1
            )

            draw_text(
                side,
                f"Capacity: {data['capacity']}",
                (190, top + 70),
                (0, 130, 190),
                0.40,
                1
            )

            draw_text(
                side,
                f"Occupancy: {data['occupancy_percent']:.1f}%",
                (20, top + 93),
                (0, 130, 190),
                0.40,
                1
            )

            draw_text(
                side,
                f"Flow: {data['flow']}",
                (205, top + 93),
                (0, 150, 170),
                0.40,
                1
            )

            draw_text(
                side,
                f"{data['flow_state']} | {data['trend']}",
                (20, top + 116),
                (80, 90, 100),
                0.37,
                1
            )

            draw_text(
                side,
                f"Risk: {data['risk']}",
                (205, top + 116),
                (80, 90, 100),
                0.37,
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
            "OVERALL CROWD INTELLIGENCE",
            (20, 29),
            (25, 35, 45),
            0.58,
            2
        )

        summary = [
            ("PEOPLE", str(total_people)),
            ("CAPACITY", str(total_capacity)),
            ("OCCUPANCY", f"{total_occupancy:.1f}%"),
            ("USABLE AREA", f"{total_usable_area:.1f} m2"),
            ("RISK", str(int(total_risk))),
            ("STATUS", overall_level),
        ]

        summary_width = 205

        for index, (label, value) in enumerate(summary):

            x = 20 + index * summary_width

            draw_text(
                bottom,
                label,
                (x, 57),
                (100, 110, 120),
                0.37,
                1
            )

            color = (35, 145, 80)

            if label == "RISK":
                if total_risk > 75:
                    color = (40, 40, 210)
                elif total_risk > 50:
                    color = (0, 120, 220)
                elif total_risk > 25:
                    color = (0, 145, 210)

            if label == "STATUS":
                if overall_level == "CRITICAL":
                    color = (40, 40, 210)
                elif overall_level == "HIGH":
                    color = (0, 120, 220)
                elif overall_level == "MODERATE":
                    color = (0, 145, 210)

            draw_text(
                bottom,
                value,
                (x, 88),
                color,
                0.58,
                2
            )

        draw_text(
            bottom,
            f"Camera: {CAMERA_NAME}",
            (20, 114),
            (100, 110, 120),
            0.34,
            1
        )

        draw_text(
            bottom,
            "F: Fullscreen    Q / ESC: Exit",
            (display_width - 240, 114),
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
