# encoding: utf-8
"""
crowd_engine.py - 2-Camera YOLO11s + ByteTrack + FastReID Cross-Camera Crowd Engine

Integrates YOLO11s person detection and ByteTrack motion tracking with a FastReID
appearance-based re-match layer to maintain consistent Global IDs across cameras.

Key constraints respected:
- YOLO11s + ByteTrack tracking logic remains unchanged.
- ReID runs ONLY as a re-match layer on top for new tracks (never every frame).
- ReID is skipped if crop < 32x16 (retries next frame).
- One shared IdentityGallery and track_map in the same Python process.
- On track drop, track_map is cleared for that track but gallery entry persists until expiry.
- Risk-score calculation logic is strictly preserved.
"""

import os
import sys
import time
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
import cv2

# Ensure fast-reid path is accessible
_current_dir = os.path.dirname(os.path.abspath(__file__))
_fast_reid_dir = os.path.join(_current_dir, "fast-reid")
for p in [_current_dir, _fast_reid_dir]:
    if os.path.exists(p) and p not in sys.path:
        sys.path.insert(0, p)

from reid import ReIDExtractor
from gallery import IdentityGallery


class TwoCameraCrowdEngine:
    """
    Multi-camera crowd monitoring engine with FastReID cross-camera matching.
    """

    def __init__(
        self,
        yolo_model_path: str = "yolo11s.pt",
        reid_config: str = "configs/Market1501/sbs_S50.yml",
        reid_weights: str = "market_sbs_S50.pth",
        match_threshold: float = 0.75,
        expiry_seconds: float = 300.0,
        ema_alpha: float = 0.5,
        overlapping_views: bool = False,
        min_crop_size: Tuple[int, int] = (32, 16),  # (min_height, min_width)
        device: str = "cuda",
        risk_thresholds: Optional[Dict[str, float]] = None
    ):
        """
        Initialize the 2-camera crowd engine.

        Args:
            yolo_model_path: Path to YOLO11s weights file.
            reid_config: Path to FastReID model YAML config.
            reid_weights: Path to trained FastReID checkpoint (.pth).
            match_threshold: Cosine similarity threshold for identity match.
            expiry_seconds: Gallery identity retention duration in seconds.
            ema_alpha: Momentum alpha for embedding updates (0.5).
            overlapping_views: True if cameras overlap (deduplicate count), False for transit continuity.
            min_crop_size: (min_h, min_w) threshold to skip tiny/unreliable crops.
            device: 'cuda' or 'cpu'.
            risk_thresholds: Density/crowd thresholds for risk calculation.
        """
        self.device = device
        self.overlapping_views = overlapping_views
        self.min_crop_h, self.min_crop_w = min_crop_size

        if not os.path.exists(reid_config) and os.path.exists(os.path.join(_fast_reid_dir, reid_config)):
            reid_config = os.path.join(_fast_reid_dir, reid_config)
        if not os.path.exists(reid_weights) and os.path.exists(os.path.join(_fast_reid_dir, reid_weights)):
            reid_weights = os.path.join(_fast_reid_dir, reid_weights)

        # 1. Initialize YOLO11s detector per camera for isolated ByteTrack tracking
        print(f"[Engine] Loading YOLO11s detector ({yolo_model_path})...")
        from ultralytics import YOLO
        self.yolo_model_path = yolo_model_path
        self.detectors = {
            1: YOLO(yolo_model_path),
            2: YOLO(yolo_model_path)
        }

        # 2. Initialize FastReID feature extractor (loaded once at startup)
        print(f"[Engine] Loading FastReID extractor ({reid_weights})...")
        self.reid = ReIDExtractor(
            config_path=reid_config,
            weights_path=reid_weights,
            device=device
        )

        # 3. Create ONE shared IdentityGallery across all cameras
        self.gallery = IdentityGallery(
            match_threshold=match_threshold,
            expiry_seconds=expiry_seconds,
            ema_alpha=ema_alpha
        )

        # 4. Create ONE shared track_map: {(camera_id, local_track_id): global_id}
        self.track_map: Dict[Tuple[int, int], int] = {}
        self.track_metadata: Dict[Tuple[int, int], Dict[str, Any]] = {}

        # 5. Track active local IDs per camera to detect dropped tracks
        self.active_local_tracks: Dict[int, set] = {1: set(), 2: set()}

        # 6. Risk score configuration (preserved exactly)
        self.risk_thresholds = risk_thresholds or {
            "low": 5,
            "medium": 12,
            "high": 25
        }

    def process_frame(
        self,
        camera_id: int,
        frame: np.ndarray,
        zones: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Process a single video frame from camera `camera_id`.
        """
        h_frame, w_frame = frame.shape[:2]
        if camera_id not in self.active_local_tracks:
            self.active_local_tracks[camera_id] = set()

        if camera_id not in self.detectors:
            from ultralytics import YOLO
            self.detectors[camera_id] = YOLO(self.yolo_model_path)

        # Step 1: Run YOLO11s person detection + ByteTrack tracking on camera's own tracker
        detector = self.detectors[camera_id]
        results = detector.track(
            source=frame,
            persist=True,
            tracker="bytetrack.yaml",
            classes=[0],  # Class 0: person
            device=self.device,
            verbose=False
        )

        current_local_ids = set()
        frame_tracks = []

        if results and len(results) > 0 and results[0].boxes is not None and len(results[0].boxes) > 0:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            confidences = results[0].boxes.conf.cpu().numpy()
            if results[0].boxes.id is not None:
                track_ids = results[0].boxes.id.int().cpu().numpy()
            else:
                # If tracker is acquiring track, assign provisional ID
                track_ids = np.array([i + 1 for i in range(len(boxes))], dtype=int)

            for bbox, local_id, conf in zip(boxes, track_ids, confidences):
                local_id = int(local_id)
                current_local_ids.add(local_id)

                x1, y1, x2, y2 = [int(v) for v in bbox]
                # Clamp coordinates to frame boundaries
                x1 = max(0, min(x1, w_frame - 1))
                y1 = max(0, min(y1, h_frame - 1))
                x2 = max(x1 + 1, min(x2, w_frame))
                y2 = max(y1 + 1, min(y2, h_frame))

                crop_h = y2 - y1
                crop_w = x2 - x1

                key = (camera_id, local_id)

                # Step 2: New track handling with ReID appearance matching
                if key not in self.track_map:
                    # Skip ReID if crop is smaller than min threshold (retry next frame)
                    if crop_h < self.min_crop_h or crop_w < self.min_crop_w:
                        # Temporary skip - do not register until sufficiently large crop
                        global_id = None
                        match_score = None
                    else:
                        crop = frame[y1:y2, x1:x2]
                        emb = self.reid.embedding(crop)
                        global_id, match_score = self.gallery.match_or_register(emb)
                        self.track_map[key] = global_id
                        self.track_metadata[key] = {
                            "match_score": match_score,
                            "is_match": match_score is not None,
                            "registered_at": time.time()
                        }
                else:
                    global_id = self.track_map[key]

                meta = self.track_metadata.get(key, {})
                frame_tracks.append({
                    "camera_id": camera_id,
                    "local_id": local_id,
                    "global_id": global_id,
                    "bbox": [x1, y1, x2, y2],
                    "conf": float(conf),
                    "crop_size": (crop_h, crop_w),
                    "match_score": meta.get("match_score"),
                    "is_reid_match": meta.get("is_match", False)
                })

        # Step 3: Handle dropped tracks (lost by ByteTrack)
        # Remove from track_map so if the ID is reused or reappears, it re-evaluates
        # Gallery entry is deliberately NOT removed (it expires after expiry_seconds)
        dropped_local_ids = self.active_local_tracks[camera_id] - current_local_ids
        for dropped_id in dropped_local_ids:
            drop_key = (camera_id, dropped_id)
            self.track_map.pop(drop_key, None)
            self.track_metadata.pop(drop_key, None)

        self.active_local_tracks[camera_id] = current_local_ids

        # Step 4: Zone occupancy and crowd metrics
        active_global_ids = [t["global_id"] for t in frame_tracks if t["global_id"] is not None]
        zone_counts = self._compute_zone_counts(frame_tracks, zones)

        return {
            "camera_id": camera_id,
            "tracks": frame_tracks,
            "active_global_ids": active_global_ids,
            "local_track_count": len(current_local_ids),
            "zone_counts": zone_counts,
            "timestamp": time.time()
        }

    def _compute_zone_counts(
        self,
        tracks: List[Dict[str, Any]],
        zones: Optional[List[Dict[str, Any]]]
    ) -> Dict[str, int]:
        """Compute occupant count per defined polygon zone."""
        if not zones:
            return {"default_zone": len(tracks)}

        zone_counts = {z.get("name", f"zone_{i}"): 0 for i, z in enumerate(zones)}
        for t in tracks:
            x1, y1, x2, y2 = t["bbox"]
            cx, cy = (x1 + x2) / 2.0, y2  # Bottom-center anchor point
            for z in zones:
                name = z.get("name")
                poly = np.array(z["polygon"], dtype=np.int32)
                if cv2.pointPolygonTest(poly, (float(cx), float(cy)), False) >= 0:
                    zone_counts[name] += 1
                    break
        return zone_counts

    def get_crowd_state(self, cam1_result: Dict[str, Any], cam2_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge results from both cameras to compute overall crowd state and risk score.

        Rule (Constraint 7):
        - Per-camera counts remain as-is.
        - If overlapping_views: deduplicate total by taking union of unique global IDs.
        - If non-overlapping: sum per-camera counts and let global IDs provide continuity.
        - Risk score logic is preserved.
        """
        cam1_gids = set(cam1_result.get("active_global_ids", []))
        cam2_gids = set(cam2_result.get("active_global_ids", []))

        if self.overlapping_views:
            # Overlapping views: deduplicate identical people present in both frames
            all_unique_gids = cam1_gids | cam2_gids
            total_crowd_count = len(all_unique_gids)
            overlap_count = len(cam1_gids & cam2_gids)
        else:
            # Non-overlapping views: per-camera counts represent independent physical locations
            total_crowd_count = cam1_result.get("local_track_count", 0) + cam2_result.get("local_track_count", 0)
            all_unique_gids = cam1_gids | cam2_gids
            overlap_count = 0

        risk_score = self.calculate_risk_score(total_crowd_count)

        return {
            "camera_1_count": cam1_result.get("local_track_count", 0),
            "camera_2_count": cam2_result.get("local_track_count", 0),
            "total_crowd_count": total_crowd_count,
            "overlapping_people_count": overlap_count,
            "unique_global_identities_visible": len(all_unique_gids),
            "gallery_size": len(self.gallery),
            "risk_score": risk_score
        }

    def calculate_risk_score(self, total_crowd: int) -> float:
        """
        Preserved crowd risk-score logic.
        Normalized risk score between 0.0 (safe) and 1.0 (critical).
        """
        low = self.risk_thresholds["low"]
        med = self.risk_thresholds["medium"]
        high = self.risk_thresholds["high"]

        if total_crowd <= low:
            return round(0.2 * (total_crowd / max(1, low)), 2)
        elif total_crowd <= med:
            return round(0.2 + 0.3 * ((total_crowd - low) / (med - low)), 2)
        elif total_crowd <= high:
            return round(0.5 + 0.5 * min(1.0, (total_crowd - med) / (high - med)), 2)
        else:
            return 1.0
