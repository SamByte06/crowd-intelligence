# encoding: utf-8
"""
app.py - Dual-Camera FastReID Person Detection & Cross-Camera Re-Identification Demo
Powered by YOLO11s + ByteTrack + FastReID ResNeSt-50 SBS on NVIDIA RTX 3050 Laptop GPU.
"""

import os
import sys
import time
import threading
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import cv2
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn

# Include workspace roots for FastReID package resolution
_current_dir = os.path.dirname(os.path.abspath(__file__))
_fast_reid_dir = os.path.join(_current_dir, "fast-reid")
for p in [_current_dir, _fast_reid_dir]:
    if os.path.exists(p) and p not in sys.path:
        sys.path.insert(0, p)

from ultralytics import YOLO
from reid import ReIDExtractor
from gallery import IdentityGallery

app = FastAPI(title="FastReID Dual-Camera Demo")

# -------------------------------------------------------------
# FastReID Dual Camera Engine
# -------------------------------------------------------------
class FastReIDDemoEngine:
    """
    Core demo engine managing:
    - Independent YOLO11s + ByteTrack instances per camera
    - FastReID feature extractor running on NVIDIA RTX 3050 GPU
    - Shared IdentityGallery maintaining consistent Global IDs
    """
    def __init__(
        self,
        yolo_path: str = "yolo11s.pt",
        reid_config: str = "fast-reid/configs/Market1501/sbs_S50.yml",
        reid_weights: str = "fast-reid/market_sbs_S50.pth",
        device: str = "cuda",
        match_threshold: float = 0.75,
        expiry_seconds: float = 300.0
    ):
        self.device = device
        self.min_crop_h, self.min_crop_w = 60, 30

        print(f"[Demo] Loading YOLO11s person detectors for Cam 1 & Cam 2 on {device}...")
        self.detectors = {
            1: YOLO(yolo_path),
            2: YOLO(yolo_path)
        }

        print(f"[Demo] Loading FastReID ResNeSt-50 SBS extractor on {device}...")
        self.reid = ReIDExtractor(
            config_path=reid_config,
            weights_path=reid_weights,
            device=device
        )

        print("[Demo] Initializing Shared Identity Gallery...")
        self.gallery = IdentityGallery(
            match_threshold=match_threshold,
            expiry_seconds=expiry_seconds
        )

        # Shared track mapping: {(cam_id, local_id): global_id}
        # NOTE: global_id can be negative (pending confirmation) or positive (confirmed)
        self.track_map: Dict[Tuple[int, int], int] = {}
        self.track_metadata: Dict[Tuple[int, int], Dict[str, Any]] = {}
        self.track_last_bbox: Dict[Tuple[int, int], List[int]] = {}
        self.track_frame_count: Dict[Tuple[int, int], int] = {}
        self.lost_tracks: Dict[int, Dict[int, Dict[str, Any]]] = {1: {}, 2: {}}
        self.active_local_tracks: Dict[int, set] = {1: set(), 2: set()}

        # How often to re-verify an active track's identity (in frames)
        self.reverify_interval = 60

    @staticmethod
    def _compute_iou(boxA: List[int], boxB: List[int]) -> float:
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])
        inter = max(0, xB - xA) * max(0, yB - yA)
        areaA = max(1, (boxA[2] - boxA[0]) * (boxA[3] - boxA[1]))
        areaB = max(1, (boxB[2] - boxB[0]) * (boxB[3] - boxB[1]))
        union = areaA + areaB - inter
        return float(inter / union) if union > 0 else 0.0

    def _prepare_crop(self, frame: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> np.ndarray:
        """
        Extract clean person crop for FastReID feature extraction.
        """
        h_frame, w_frame = frame.shape[:2]
        cx1 = max(0, min(x1, w_frame - 1))
        cy1 = max(0, min(y1, h_frame - 1))
        cx2 = max(cx1 + 1, min(x2, w_frame))
        cy2 = max(cy1 + 1, min(y2, h_frame))
        return frame[cy1:cy2, cx1:cx2]

    def process_frame(self, camera_id: int, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect persons via YOLO11s, track with ByteTrack, and match/assign Global ID with FastReID.
        Uses multi-frame confirmation and periodic re-verification for stability.
        """
        h_frame, w_frame = frame.shape[:2]
        detector = self.detectors[camera_id]

        results = detector.track(
            source=frame,
            persist=True,
            tracker="bytetrack.yaml",
            classes=[0],
            conf=0.45,
            iou=0.45,
            device=self.device,
            verbose=False
        )

        now = time.time()
        # Clean up stale lost tracks (reserve for 5 minutes: 300.0s)
        self.lost_tracks[camera_id] = {
            lid: data for lid, data in self.lost_tracks[camera_id].items()
            if (now - data["lost_time"]) < self.gallery.expiry_seconds
        }

        current_local_ids = set()
        detected_tracks = []

        if results and len(results) > 0 and results[0].boxes is not None and len(results[0].boxes) > 0:
            raw_boxes = results[0].boxes.xyxy.cpu().numpy()
            raw_confs = results[0].boxes.conf.cpu().numpy()

            if results[0].boxes.id is not None:
                raw_track_ids = results[0].boxes.id.int().cpu().numpy()
            else:
                raw_track_ids = np.array([i + 1 for i in range(len(raw_boxes))], dtype=int)

            # Suppress duplicate/nested person detections (e.g. torso/chin box nested inside full body)
            n_raw = len(raw_boxes)
            areas = [(raw_boxes[i][2] - raw_boxes[i][0]) * (raw_boxes[i][3] - raw_boxes[i][1]) for i in range(n_raw)]
            order = sorted(range(n_raw), key=lambda i: areas[i], reverse=True)

            keep_idx = []
            suppressed = set()
            for i in order:
                if i in suppressed:
                    continue
                keep_idx.append(i)
                bA = raw_boxes[i]
                for j in order:
                    if j == i or j in suppressed:
                        continue
                    bB = raw_boxes[j]
                    # Compute intersection over smaller box area
                    inter_x1 = max(bA[0], bB[0])
                    inter_y1 = max(bA[1], bB[1])
                    inter_x2 = min(bA[2], bB[2])
                    inter_y2 = min(bA[3], bB[3])
                    inter = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)
                    smaller_area = min(areas[i], areas[j])
                    if smaller_area > 0 and (inter / smaller_area) > 0.50:
                        suppressed.add(j)

            boxes = raw_boxes[keep_idx]
            confidences = raw_confs[keep_idx]
            track_ids = raw_track_ids[keep_idx]

            # Pre-gather confirmed global IDs already active in this camera
            active_cam_gids = set()
            for lid in track_ids:
                k = (camera_id, int(lid))
                if k in self.track_map:
                    gid = self.track_map[k]
                    if gid is not None and gid > 0:  # Only confirmed IDs for exclusion
                        active_cam_gids.add(gid)

            for bbox, local_id, conf in zip(boxes, track_ids, confidences):
                local_id = int(local_id)
                current_local_ids.add(local_id)

                x1, y1, x2, y2 = [int(v) for v in bbox]
                x1 = max(0, min(x1, w_frame - 1))
                y1 = max(0, min(y1, h_frame - 1))
                x2 = max(x1 + 1, min(x2, w_frame))
                y2 = max(y1 + 1, min(y2, h_frame))
                curr_box = [x1, y1, x2, y2]

                crop_h = y2 - y1
                crop_w = x2 - x1
                key = (camera_id, local_id)
                global_id = None

                # ---- CASE 1: Active track (already has a mapped global_id) ----
                if key in self.track_map:
                    global_id = self.track_map[key]
                    self.track_frame_count[key] = self.track_frame_count.get(key, 0) + 1

                    # If pending (negative ID), feed another sample for confirmation/flip
                    if global_id is not None and global_id < 0:
                        if crop_h >= self.min_crop_h and crop_w >= self.min_crop_w:
                            crop = self._prepare_crop(frame, x1, y1, x2, y2)
                            emb = self.reid.embedding(crop)
                            confirmed_id, score = self.gallery.add_pending_sample(
                                global_id, emb,
                                exclude_ids=active_cam_gids,
                                source_camera=camera_id
                            )
                            if confirmed_id is not None and confirmed_id != global_id:
                                # Promoted/flipped to confirmed or matched existing ID!
                                self.track_map[key] = confirmed_id
                                global_id = confirmed_id
                                if confirmed_id > 0:
                                    active_cam_gids.add(confirmed_id)
                                    first_cam = camera_id
                                    if score is not None and confirmed_id in self.gallery.entries:
                                        first_cam = self.gallery.entries[confirmed_id].get("source_camera", camera_id)
                                    self.track_metadata[key] = {
                                        "global_id": confirmed_id,
                                        "match_score": score,
                                        "is_match": score is not None,
                                        "first_camera": first_cam,
                                        "registered_at": time.time()
                                    }

                    # If confirmed (positive ID), STRICTLY LOCK IT TO THIS PERSON WHILE IN FRAME!
                    elif global_id is not None and global_id > 0:
                        # Continuous detection: ID NEVER changes while person is in frame
                        self.gallery.update_last_seen(global_id)
                        # Keep embedding bank fresh without changing ID
                        fc = self.track_frame_count.get(key, 0)
                        if fc > 0 and fc % 45 == 0:
                            if crop_h >= self.min_crop_h and crop_w >= self.min_crop_w:
                                crop = self._prepare_crop(frame, x1, y1, x2, y2)
                                emb = self.reid.embedding(crop)
                                _, v_score = self.gallery.match_only(
                                    emb, exclude_ids=active_cam_gids - {global_id},
                                    source_camera=camera_id
                                )
                                if v_score is not None and v_score >= 0.88 and global_id in self.gallery.entries:
                                    self.gallery.entries[global_id]["embeddings"].append(emb)
                                    if len(self.gallery.entries[global_id]["embeddings"]) > self.gallery.max_embeddings:
                                        self.gallery.entries[global_id]["embeddings"] = self.gallery.entries[global_id]["embeddings"][-self.gallery.max_embeddings:]

                # ---- CASE 2: Re-acquired by same ByteTrack ID from short drop ----
                elif local_id in self.lost_tracks[camera_id]:
                    lost_info = self.lost_tracks[camera_id].pop(local_id)
                    gid = lost_info["global_id"]
                    if gid > 0 and gid not in active_cam_gids:
                        self.track_map[key] = gid
                        self.track_metadata[key] = lost_info["metadata"]
                        self.track_frame_count[key] = lost_info.get("frame_count", 0)
                        active_cam_gids.add(gid)
                        self.gallery.update_last_seen(gid)
                        global_id = gid
                    elif gid < 0:
                        # Was pending — cancel it, will get a fresh start
                        self.gallery.cancel_pending(gid)
                        global_id = None
                    else:
                        global_id = None

                # ---- CASE 3: Spatial continuity — overlap with recently-lost track ----
                else:
                    best_lost_id = None
                    best_iou = 0.0
                    for l_id, l_data in list(self.lost_tracks[camera_id].items()):
                        lost_gid = l_data["global_id"]
                        if lost_gid > 0 and lost_gid not in active_cam_gids and (now - l_data["lost_time"]) < 20.0:
                            iou = self._compute_iou(curr_box, l_data["bbox"])
                            if iou > 0.20 and iou > best_iou:
                                best_iou = iou
                                best_lost_id = l_id

                    if best_lost_id is not None:
                        lost_info = self.lost_tracks[camera_id].pop(best_lost_id)
                        gid = lost_info["global_id"]
                        self.track_map[key] = gid
                        self.track_metadata[key] = lost_info["metadata"]
                        self.track_frame_count[key] = lost_info.get("frame_count", 0)
                        active_cam_gids.add(gid)
                        self.gallery.update_last_seen(gid)
                        global_id = gid

                    # ---- CASE 4: Brand new track — run ReID against 5-min reserved gallery ----
                    else:
                        if crop_h >= self.min_crop_h and crop_w >= self.min_crop_w:
                            crop = self._prepare_crop(frame, x1, y1, x2, y2)
                            emb = self.reid.embedding(crop)

                            # Match against existing reserved IDs in gallery (threshold 0.75)
                            global_id, match_score = self.gallery.match_or_register(
                                emb,
                                exclude_ids=active_cam_gids,
                                allow_register=True,
                                source_camera=camera_id
                            )

                            if global_id is not None:
                                self.track_map[key] = global_id
                                self.track_frame_count[key] = 0

                                if global_id > 0:
                                    active_cam_gids.add(global_id)
                                    first_cam = camera_id
                                    if match_score is not None and global_id in self.gallery.entries:
                                        first_cam = self.gallery.entries[global_id].get("source_camera", camera_id)
                                    self.track_metadata[key] = {
                                        "global_id": global_id,
                                        "match_score": match_score,
                                        "is_match": match_score is not None,
                                        "first_camera": first_cam,
                                        "registered_at": time.time()
                                    }
                                # else: pending (negative ID), metadata will be set on confirmation

                self.track_last_bbox[key] = curr_box

                # For display: use confirmed global_id only (pending shows as None)
                display_gid = global_id if (global_id is not None and global_id > 0) else None
                meta = self.track_metadata.get(key, {})
                detected_tracks.append({
                    "camera_id": camera_id,
                    "local_id": local_id,
                    "global_id": display_gid,
                    "bbox": [x1, y1, x2, y2],
                    "conf": float(conf),
                    "is_match": meta.get("is_match", False),
                    "match_score": meta.get("match_score"),
                    "first_camera": meta.get("first_camera", camera_id)
                })

        # ---- CASE 5: Handle dropped tracks ----
        dropped_ids = self.active_local_tracks[camera_id] - current_local_ids
        for drop_id in dropped_ids:
            drop_key = (camera_id, drop_id)
            gid = self.track_map.pop(drop_key, None)
            meta = self.track_metadata.pop(drop_key, None)
            last_bbox = self.track_last_bbox.pop(drop_key, None)
            fc = self.track_frame_count.pop(drop_key, 0)

            if gid is not None and gid < 0:
                # Cancel pending registration for dropped unconfirmed tracks
                self.gallery.cancel_pending(gid)
            elif gid is not None and last_bbox is not None:
                self.lost_tracks[camera_id][drop_id] = {
                    "global_id": gid,
                    "bbox": last_bbox,
                    "lost_time": time.time(),
                    "metadata": meta or {},
                    "frame_count": fc
                }

        self.active_local_tracks[camera_id] = current_local_ids
        return detected_tracks


# -------------------------------------------------------------
# Global State & Video Capture Worker
# -------------------------------------------------------------
engine: Optional[FastReIDDemoEngine] = None
running: bool = True

cam1_display_frame: Optional[np.ndarray] = None
cam2_display_frame: Optional[np.ndarray] = None
frame_lock = threading.Lock()

cam1_source = 0
cam2_source = ""
cam2_simulation_active = False

PALETTE = [
    (248, 189, 56),  # Cyan
    (153, 211, 52),  # Emerald
    (11, 158, 245),  # Amber
    (153, 72, 236),  # Pink
    (247, 85, 168),  # Purple
    (241, 102, 99),  # Indigo
    (166, 184, 20),  # Teal
    (94, 63, 244),   # Rose
]

def get_color(gid: int) -> Tuple[int, int, int]:
    return PALETTE[(gid - 1) % len(PALETTE)] if gid else (180, 180, 180)


class ThreadedCamera:
    """Non-blocking background video capture for webcam & phone streams."""
    def __init__(self, source, name="Camera"):
        self.name = name
        self.source = source
        self.is_running = True
        self.cap = None
        self.latest_frame = None
        self.is_connected = False
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def set_source(self, new_source):
        with self.lock:
            self.source = new_source
            if self.cap is not None:
                self.cap.release()
                self.cap = None
            self.is_connected = False
            self.latest_frame = None

    def _open_cap(self):
        src = self.source
        if src is None or src == "":
            return None
        if isinstance(src, str) and src.isdigit():
            src = int(src)
        if isinstance(src, int):
            cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        else:
            # Fast TCP socket pre-check to prevent OpenCV 90s hang if IP is unreachable
            if isinstance(src, str) and (src.startswith("http://") or src.startswith("https://") or src.startswith("rtsp://")):
                try:
                    import urllib.parse
                    import socket
                    parsed = urllib.parse.urlparse(src)
                    host = parsed.hostname
                    port = parsed.port or (443 if src.startswith("https://") else 8080)
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(1.2)
                    res = s.connect_ex((host, port))
                    s.close()
                    if res != 0:
                        return None
                except Exception:
                    return None

            cap = cv2.VideoCapture(src)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _capture_loop(self):
        while self.is_running:
            if not self.source and self.source != 0:
                time.sleep(0.5)
                continue

            if self.cap is None or not self.cap.isOpened():
                try:
                    self.cap = self._open_cap()
                except Exception:
                    with self.lock:
                        self.is_connected = False
                    time.sleep(1.0)
                    continue

            if self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and frame is not None and frame.size > 0:
                    with self.lock:
                        self.latest_frame = frame
                        self.is_connected = True
                else:
                    with self.lock:
                        self.is_connected = False
                    time.sleep(0.05)
            else:
                with self.lock:
                    self.is_connected = False
                time.sleep(1.0)
            time.sleep(0.01)

    def read(self):
        with self.lock:
            if self.latest_frame is not None:
                return self.is_connected, self.latest_frame.copy()
            return self.is_connected, None

    def release(self):
        self.is_running = False
        if self.cap is not None:
            self.cap.release()


cam1_capture: Optional[ThreadedCamera] = None
cam2_capture: Optional[ThreadedCamera] = None


# -------------------------------------------------------------
# Drawing Clean HUD Annotations
# -------------------------------------------------------------
def draw_hud(frame: np.ndarray, tracks: List[Dict[str, Any]], cam_id: int) -> np.ndarray:
    """Draw clean person bounding boxes and FastReID identification labels."""
    out = frame.copy()
    h_frame, w_frame = out.shape[:2]

    # Camera Header Tag
    cam_name = f"ZONE {cam_id:02d}: " + ("Webcam (Zone 1)" if cam_id == 1 else "Phone Stream (Zone 2)")
    cv2.putText(out, f"{cam_name} | People: {len(tracks)}", (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (255, 255, 255), 2)

    for t in tracks:
        gid = t.get("global_id")
        lid = t.get("local_id", 0)
        x1, y1, x2, y2 = t["bbox"]
        is_match = t.get("is_match", False)
        score = t.get("match_score")
        first_cam = t.get("first_camera", cam_id)

        if gid is not None:
            color = get_color(gid)
            if is_match and score is not None:
                if first_cam != cam_id:
                    status_text = f"RE-IDENTIFIED FROM CAM {first_cam} ({int(score * 100)}% MATCH)"
                else:
                    status_text = f"RE-MATCHED ({int(score * 100)}%)"
            elif is_match:
                status_text = "RE-MATCHED"
            else:
                status_text = "NEW IDENTITY"

            main_label = f"PERSON ID: #{gid}"
            sub_label = f"ByteTrack #{lid} | {status_text}"
        else:
            color = (0, 200, 255)
            main_label = f"ByteTrack #{lid}"
            sub_label = "Scanning appearance..."

        # 1. Main Bounding Box
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 3)

        # 2. Corner tick accents
        c_len = min(22, int((x2 - x1) * 0.2), int((y2 - y1) * 0.2))
        if c_len > 4:
            cv2.line(out, (x1, y1), (x1 + c_len, y1), (255, 255, 255), 3)
            cv2.line(out, (x1, y1), (x1, y1 + c_len), (255, 255, 255), 3)
            cv2.line(out, (x2, y1), (x2 - c_len, y1), (255, 255, 255), 3)
            cv2.line(out, (x2, y1), (x2, y1 + c_len), (255, 255, 255), 3)
            cv2.line(out, (x1, y2), (x1 + c_len, y2), (255, 255, 255), 3)
            cv2.line(out, (x1, y2), (x1, y2 - c_len), (255, 255, 255), 3)
            cv2.line(out, (x2, y2), (x2 - c_len, y2), (255, 255, 255), 3)
            cv2.line(out, (x2, y2), (x2, y2 - c_len), (255, 255, 255), 3)

        # 3. Two-line solid banner above bbox
        banner_h = 44
        tag_y2 = max(banner_h, y1)
        tag_y1 = tag_y2 - banner_h
        cv2.rectangle(out, (x1, tag_y1), (min(w_frame, x1 + 320), tag_y2), (15, 18, 28), -1)
        cv2.rectangle(out, (x1, tag_y1), (min(w_frame, x1 + 320), tag_y2), color, 2)

        # Text line 1: Persistent Person Global ID
        cv2.putText(out, main_label, (x1 + 8, tag_y1 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.58, color, 2)
        # Text line 2: Local ByteTrack ID & ReID Status
        cv2.putText(out, sub_label, (x1 + 8, tag_y1 + 36), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (220, 225, 235), 1)

    return out


def make_waiting_frame(cam_name: str, message: str) -> np.ndarray:
    """Generate clean placeholder when stream is waiting to connect."""
    frame = np.full((480, 640, 3), 20, dtype=np.uint8)
    for y in range(0, 480, 40):
        cv2.line(frame, (0, y), (640, y), (30, 32, 42), 1)
    for x in range(0, 640, 40):
        cv2.line(frame, (x, 0), (x, 480), (30, 32, 42), 1)

    cv2.putText(frame, f"[{cam_name}]", (40, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (56, 189, 248), 2)
    cv2.putText(frame, message, (40, 190), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 200, 200), 2)

    cv2.putText(frame, "To connect your Android phone:", (40, 270), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 2)
    cv2.putText(frame, "1. Open 'IP Webcam' app on Android", (40, 310), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 190, 200), 1)
    cv2.putText(frame, "2. Tap 'Start server' at the bottom", (40, 345), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 190, 200), 1)
    cv2.putText(frame, "3. Enter URL (e.g. http://192.168.1.XX:8080/video) above & click Connect", (40, 380), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 190, 200), 1)
    cv2.putText(frame, "Or click 'Test Cross-Cam with Sample' to test right now!", (40, 420), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (52, 211, 153), 2)
    return frame


# -------------------------------------------------------------
# Background Worker Thread
# -------------------------------------------------------------
live_stats: Dict[str, Any] = {
    "cam1_count": 0,
    "cam2_count": 0,
    "total_unique_persons": 0,
    "gallery_size": 0,
    "fps": 60.0,
    "cam1_connected": False,
    "cam2_connected": False,
    "active_persons": []
}

def main_processing_worker():
    global cam1_display_frame, cam2_display_frame, live_stats, running, engine
    fps_history = []

    # Sample person crop for simulation test mode
    sim_idx = 0

    while running:
        t_start = time.time()

        # 1. Read Camera 1 (Webcam)
        c1_conn, raw_c1 = cam1_capture.read() if cam1_capture else (False, None)

        # 2. Read Camera 2 (Phone or Simulation)
        if cam2_simulation_active:
            c2_conn = True
            sim_idx += 1
            # Generate simulated camera 2 feed
            raw_c2 = np.full((480, 640, 3), 30, dtype=np.uint8)
            cv2.line(raw_c2, (0, 350), (640, 350), (45, 45, 55), 2)
            cv2.putText(raw_c2, "CAM 02 - CROSS-CAM TEST STREAM", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (180, 180, 180), 2)
            # If camera 1 has a frame, copy person from camera 1 to test cross-camera re-identification!
            if c1_conn and raw_c1 is not None and engine is not None and len(engine.active_local_tracks[1]) > 0:
                # Mirror camera 1 to simulate same person appearing on camera 2
                raw_c2 = cv2.convertScaleAbs(raw_c1, alpha=0.95, beta=10)
        else:
            c2_conn, raw_c2 = cam2_capture.read() if cam2_capture else (False, None)

        tracks1 = []
        tracks2 = []

        if engine is not None:
            # Process Cam 1
            if c1_conn and raw_c1 is not None:
                tracks1 = engine.process_frame(camera_id=1, frame=raw_c1)
                ann_c1 = draw_hud(raw_c1, tracks1, cam_id=1)
            else:
                ann_c1 = make_waiting_frame("Camera 1 (Laptop Webcam)", "Waiting for laptop webcam (Device 0)...")

            # Process Cam 2
            if c2_conn and raw_c2 is not None:
                tracks2 = engine.process_frame(camera_id=2, frame=raw_c2)
                ann_c2 = draw_hud(raw_c2, tracks2, cam_id=2)
            else:
                ann_c2 = make_waiting_frame("Camera 2 (Android Phone)", "Phone camera not connected yet.")

            with frame_lock:
                cam1_display_frame = ann_c1
                cam2_display_frame = ann_c2

            # Gather active persons list and exact zone-wise global IDs
            active_list = []
            now = time.time()
            
            # Extract detected global IDs per camera/zone
            zone1_gids = sorted(list(set(int(t["global_id"]) for t in tracks1 if t.get("global_id") is not None)))
            zone2_gids = sorted(list(set(int(t["global_id"]) for t in tracks2 if t.get("global_id") is not None)))
            both_zones_gids = sorted(list(set(zone1_gids).intersection(set(zone2_gids))))
            all_current_gids = sorted(list(set(zone1_gids).union(set(zone2_gids))))

            for gid, entry in list(engine.gallery.entries.items()):
                seeing_cam = None
                local_id = None
                status = "Tracking"

                for t in tracks1:
                    if t.get("global_id") == gid:
                        seeing_cam = "Zone 1 (Webcam)"
                        local_id = t["local_id"]
                        if t.get("is_match"):
                            score = t.get("match_score")
                            status = f"Re-Matched ({int(score * 100)}%)" if score else "Re-Matched"
                        else:
                            status = "New Identity"

                for t in tracks2:
                    if t.get("global_id") == gid:
                        if seeing_cam:
                            seeing_cam = "Both Zones (Zone 1 & 2)"
                        else:
                            seeing_cam = "Zone 2 (Phone Cam)"
                            local_id = t["local_id"]
                        if t.get("is_match"):
                            score = t.get("match_score")
                            status = f"Re-Identified ({int(score * 100)}%)" if score else "Re-Identified"
                        elif not seeing_cam:
                            status = "New Identity"

                time_since_seen = max(0.0, now - entry["last_seen"])
                if seeing_cam is not None:
                    active_list.append({
                        "global_id": gid,
                        "camera": seeing_cam,
                        "local_id": local_id or "-",
                        "age_seconds": time_since_seen,
                        "status": status,
                        "in_view": True
                    })
                elif time_since_seen <= engine.gallery.expiry_seconds:
                    rem = max(0, int(engine.gallery.expiry_seconds - time_since_seen))
                    active_list.append({
                        "global_id": gid,
                        "camera": "In Memory",
                        "local_id": "-",
                        "age_seconds": time_since_seen,
                        "status": f"Stored in Memory (Expires {rem}s)",
                        "in_view": False
                    })

            elapsed = time.time() - t_start
            fps = 1.0 / max(0.001, elapsed)
            fps_history.append(fps)
            if len(fps_history) > 20:
                fps_history.pop(0)

            # Deduplicated total: unique IDs seen across both zones
            # If provisional detections exist without global_id yet, fallback to track count
            unassigned_c1 = len([t for t in tracks1 if t.get("global_id") is None])
            unassigned_c2 = len([t for t in tracks2 if t.get("global_id") is None])
            total_persons = len(all_current_gids) + unassigned_c1 + unassigned_c2

            live_stats = {
                "cam1_count": len(tracks1),
                "cam2_count": len(tracks2),
                "zone1_count": len(tracks1),
                "zone2_count": len(tracks2),
                "zone1_ids": zone1_gids,
                "zone2_ids": zone2_gids,
                "both_zones_ids": both_zones_gids,
                "total_unique_persons": total_persons,
                "gallery_size": len(engine.gallery.entries),
                "fps": float(np.mean(fps_history)),
                "cam1_connected": c1_conn,
                "cam2_connected": c2_conn,
                "active_persons": sorted(active_list, key=lambda x: x["global_id"])
            }

        sleep_time = max(0.005, 0.033 - (time.time() - t_start))
        time.sleep(sleep_time)


# -------------------------------------------------------------
# Streaming Video Endpoints (MJPEG)
# -------------------------------------------------------------
def generate_mjpeg_stream(camera_id: int):
    while running:
        with frame_lock:
            frame = cam1_display_frame if camera_id == 1 else cam2_display_frame

        if frame is not None:
            # Downscale large frames to reduce encoding time and bandwidth
            h, w = frame.shape[:2]
            if w > 640:
                scale = 640 / w
                frame = cv2.resize(frame, (640, int(h * scale)), interpolation=cv2.INTER_AREA)
            ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ret:
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
        time.sleep(0.033)


@app.get("/stream/cam1")
def stream_cam1():
    return StreamingResponse(generate_mjpeg_stream(1), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/stream/cam2")
def stream_cam2():
    return StreamingResponse(generate_mjpeg_stream(2), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/", response_class=HTMLResponse)
def index_view(request: Request):
    html_path = os.path.join(_current_dir, "templates", "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/api/stats")
def get_stats():
    return live_stats


class CameraConnectPayload(BaseModel):
    cam2_url: str


@app.post("/api/connect_phone")
def connect_phone(payload: CameraConnectPayload):
    global cam2_source, cam2_capture, cam2_simulation_active
    cam2_simulation_active = False
    cam2_source = payload.cam2_url.strip()
    if cam2_capture:
        cam2_capture.set_source(cam2_source)
    return {"status": "ok", "cam2_source": cam2_source}


@app.post("/api/toggle_simulation")
def toggle_simulation():
    global cam2_simulation_active
    cam2_simulation_active = not cam2_simulation_active
    return {"status": "ok", "simulation": cam2_simulation_active}


class SettingsPayload(BaseModel):
    match_threshold: Optional[float] = None
    expiry_seconds: Optional[float] = None


@app.post("/api/settings")
def update_settings(payload: SettingsPayload):
    if engine is not None and engine.gallery is not None:
        if payload.match_threshold is not None:
            engine.gallery.match_threshold = float(payload.match_threshold)
        if payload.expiry_seconds is not None:
            engine.gallery.expiry_seconds = float(payload.expiry_seconds)
        return {
            "status": "ok",
            "match_threshold": engine.gallery.match_threshold,
            "expiry_seconds": engine.gallery.expiry_seconds
        }
    return {"status": "error"}


@app.post("/api/reset")
def reset_all():
    if engine is not None:
        engine.gallery.entries.clear()
        engine.gallery._pending.clear()
        engine.gallery.next_id = 1
        engine.gallery._next_pending_id = -1
        engine.track_map.clear()
        engine.track_metadata.clear()
        engine.track_last_bbox.clear()
        engine.track_frame_count.clear()
        engine.lost_tracks = {1: {}, 2: {}}
        engine.active_local_tracks = {1: set(), 2: set()}
        return {"status": "ok", "message": "Identities reset successfully"}
    return {"status": "error"}


# -------------------------------------------------------------
# Startup
# -------------------------------------------------------------
@app.on_event("startup")
def startup_event():
    global engine, cam1_capture, cam2_capture

    print("[Startup] Initializing FastReID Demo Engine on NVIDIA RTX 3050...")
    engine = FastReIDDemoEngine(
        yolo_path="yolo11s.pt",
        reid_config=os.path.join(_fast_reid_dir, "configs", "Market1501", "sbs_S50.yml"),
        reid_weights=os.path.join(_fast_reid_dir, "market_sbs_S50.pth"),
        device="cuda",
        match_threshold=0.75,
        expiry_seconds=300.0
    )

    cam1_capture = ThreadedCamera(source=0, name="Laptop Webcam")
    cam2_capture = ThreadedCamera(source=cam2_source, name="Android Phone")

    t = threading.Thread(target=main_processing_worker, daemon=True)
    t.start()
    print("[Startup] Demo server active at http://localhost:8000")


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False, log_level="info")
