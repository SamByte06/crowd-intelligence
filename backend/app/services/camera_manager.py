"""
Camera Manager — Manages independent camera processing workers.

Each camera runs in its own thread with YOLO detection, tracking, and
line-crossing counting. Camera failures don't affect other cameras.
"""

import logging
import os
import re
import threading
import time
import queue
from datetime import datetime, timezone
from typing import Optional, Callable

import cv2
import numpy as np

from app.config import settings
from app.services.gate_counter import GateCounter, LineCrossingConfig, CrossingEvent
from app.models.gate import GateStatus

logger = logging.getLogger(__name__)

MEDIA_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "media_cache")
_model_init_lock = threading.Lock()


def resolve_youtube_source(url: str) -> str:
    """
    Downloads or resolves a YouTube URL into a reliable local video file or stream URL.
    Prefers downloading into media_cache so OpenCV can seek and loop it reliably.
    """
    try:
        os.makedirs(MEDIA_CACHE_DIR, exist_ok=True)
    except Exception:
        pass

    # Extract clean video ID if possible
    video_id = None
    m = re.search(r"(?:v=|\/|youtu\.be\/)([0-9A-Za-z_-]{11})", url)
    if m:
        video_id = m.group(1)
        # Check if already cached
        for ext in ["mp4", "mkv", "webm"]:
            cached_path = os.path.join(MEDIA_CACHE_DIR, f"{video_id}.{ext}")
            if os.path.exists(cached_path) and os.path.getsize(cached_path) > 10000:
                logger.info(f"Using cached YouTube video: {cached_path}")
                return cached_path

    try:
        import yt_dlp
        target_template = os.path.join(MEDIA_CACHE_DIR, "%(id)s.%(ext)s")
        ydl_opts = {
            'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[ext=mp4]/best',
            'outtmpl': target_template,
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Downloading YouTube video clip for gate stream: {url}")
            info = ydl.extract_info(url, download=True)
            if info:
                vid = info.get("id") or video_id
                ext = info.get("ext") or "mp4"
                downloaded_file = os.path.join(MEDIA_CACHE_DIR, f"{vid}.{ext}")
                if os.path.exists(downloaded_file):
                    logger.info(f"Downloaded and cached YouTube video: {downloaded_file}")
                    return downloaded_file
                # Fallback to direct stream url
                stream_url = info.get("url")
                if not stream_url and "formats" in info:
                    for f in reversed(info["formats"]):
                        if f.get("vcodec") != "none" and f.get("url"):
                            stream_url = f.get("url")
                            break
                if stream_url:
                    return stream_url
    except Exception as e:
        logger.warning(f"Could not download YouTube video via yt-dlp: {e}")
        try:
            import yt_dlp
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'noplaylist': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                stream_url = info.get("url")
                if not stream_url and "formats" in info:
                    for f in reversed(info["formats"]):
                        if f.get("vcodec") != "none" and f.get("url"):
                            stream_url = f.get("url")
                            break
                if stream_url:
                    return stream_url
        except Exception as e2:
            logger.error(f"Failed fallback YouTube extraction: {e2}")

    return url


class CameraWorker:
    """
    Processes a single camera stream: capture → detect → track → count.

    Runs in its own thread. Failures are contained and reconnection is attempted
    with bounded exponential backoff.
    """

    def __init__(
        self,
        gate_id: str,
        venue_id: str,
        camera_source: str | int,
        gate_counter: GateCounter,
        on_crossing: Callable[[str, str, CrossingEvent], None],
        on_status_change: Callable[[str, str, str | None], None],
        model=None,
        model_getter: Optional[Callable] = None,
        confidence: float = 0.25,
        imgsz: int = 640,
        frame_skip: int = 1,
        tracker_config: str = "bytetrack.yaml",
        gate_name: str = "",
    ):
        self.gate_id = gate_id
        self.venue_id = venue_id
        self.camera_source = camera_source
        self.gate_counter = gate_counter
        self.on_crossing = on_crossing
        self.on_status_change = on_status_change
        self.model = model
        self.model_getter = model_getter
        self.confidence = confidence
        self.imgsz = imgsz
        self.frame_skip = frame_skip
        self.tracker_config = tracker_config
        self.gate_name = gate_name

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False
        self._cap: Optional[cv2.VideoCapture] = None

        # Health metrics
        self.status = GateStatus.INACTIVE
        self.last_frame_at: Optional[datetime] = None
        self.last_count_at: Optional[datetime] = None
        self.error_message: Optional[str] = None
        self.reconnect_attempts = 0
        self.frames_processed = 0
        self._latest_jpeg: Optional[bytes] = None
        self._frame_lock = threading.Lock()
        self._is_head_model = True

    def start(self):
        """Start the camera processing thread."""
        if self._running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"cam-{self.gate_id[:8]}")
        self._running = True
        self._thread.start()
        logger.info(f"Camera worker started for gate {self.gate_id}")

    def stop(self):
        """Stop the camera processing thread."""
        self._stop_event.set()
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        self._release_capture()
        self._set_status(GateStatus.INACTIVE)
        logger.info(f"Camera worker stopped for gate {self.gate_id}")

    def _run(self):
        """Main processing loop with reconnection and immediate frame preview."""
        while not self._stop_event.is_set():
            try:
                self._set_status(GateStatus.CONNECTING)
                if not self._connect():
                    self._reconnect_backoff()
                    continue

                # Publish initial preview frame immediately within 5ms of opening stream (0.1s render)
                if self._cap and self._cap.isOpened() and self._latest_jpeg is None:
                    try:
                        ret, first_frame = self._cap.read()
                        if ret and first_frame is not None:
                            small = self._resize_for_stream(first_frame)
                            annotated = self._annotate_frame_fast(small, [])
                            ok, buf = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
                            if ok:
                                with self._frame_lock:
                                    self._latest_jpeg = buf.tobytes()
                    except Exception as e:
                        logger.debug(f"Immediate preview generation: {e}")

                # Load YOLO model instance if not yet initialized
                if self.model is None and self.model_getter:
                    try:
                        self.model = self.model_getter()
                    except Exception as e:
                        logger.error(f"Failed to obtain YOLO model in worker: {e}")

                if self.model is not None and hasattr(self.model, "names"):
                    self._is_head_model = len(self.model.names) == 1 or "head" in str(self.model.names).lower()

                self._set_status(GateStatus.ACTIVE)
                self.reconnect_attempts = 0
                self._process_loop()
                if not self._stop_event.is_set():
                    self._reconnect_backoff()

            except Exception as e:
                logger.error(f"Camera worker error (gate {self.gate_id}): {e}")
                self.error_message = str(e)
                self._set_status(GateStatus.ERROR, str(e))
                self._reconnect_backoff()
            finally:
                self._release_capture()

        self._set_status(GateStatus.INACTIVE)

    def _is_loopable(self) -> bool:
        """Check if source is a local video file or cached clip that can be looped."""
        if isinstance(self.camera_source, str):
            src = self.camera_source.strip().lower()
            if not src.isdigit() and not src.startswith("rtsp://") and not src.startswith("rtmp://"):
                return True
        return False

    def _connect(self) -> bool:
        """Open the camera source."""
        try:
            source = self.camera_source
            if isinstance(source, str):
                source = source.strip().strip('"').strip("'")

            if isinstance(source, str) and source.isdigit():
                source = int(source)
            elif isinstance(source, str) and ("youtube.com" in source or "youtu.be" in source):
                self._set_status(GateStatus.CONNECTING, "Downloading/resolving YouTube video...")
                resolved = resolve_youtube_source(source)
                if resolved:
                    source = resolved
            elif isinstance(source, str) and not source.startswith(("rtsp://", "rtmp://", "http://", "https://")):
                # Local video file: verify path exists
                if os.path.exists(source):
                    source = os.path.abspath(source)
                elif os.path.exists(os.path.abspath(source)):
                    source = os.path.abspath(source)
                else:
                    self.error_message = f"Local video file not found: {source}"
                    logger.warning(self.error_message)
                    return False

            if isinstance(source, int) and hasattr(cv2, "CAP_DSHOW"):
                self._cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
            else:
                self._cap = cv2.VideoCapture(source)
            if not self._cap or not self._cap.isOpened():
                self.error_message = f"Cannot open camera source: {self.camera_source}"
                logger.warning(self.error_message)
                return False

            logger.info(f"Camera connected for gate {self.gate_id}: {self.camera_source}")
            self.error_message = None
            return True

        except Exception as e:
            self.error_message = f"Connection error: {e}"
            logger.error(self.error_message)
            return False

    def _process_loop(self):
        """Read frames, detect, track, count — optimized for low-latency tunnel streaming."""
        frame_count = 0
        last_detections: list[dict] = []
        last_encode_time = 0.0

        while not self._stop_event.is_set():
            if not self._cap or not self._cap.isOpened():
                self._set_status(GateStatus.DISCONNECTED)
                break

            ret, frame = self._cap.read()
            if not ret:
                if self._is_loopable():
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    time.sleep(0.03)
                    continue
                self._set_status(GateStatus.DISCONNECTED)
                break

            now = time.time()
            self.last_frame_at = datetime.now(timezone.utc)
            frame_count += 1

            # 1. Publish first frame immediately
            if self._latest_jpeg is None:
                try:
                    small = self._resize_for_stream(frame)
                    annotated = self._annotate_frame_fast(small, [])
                    success, buf = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 55])
                    if success:
                        with self._frame_lock:
                            self._latest_jpeg = buf.tobytes()
                except Exception as e:
                    logger.debug(f"Initial frame publication: {e}")

            # 2. Run detection every frame_skip frames
            should_detect = (frame_count % self.frame_skip == 0)
            if should_detect and self.model is not None:
                self.frames_processed += 1
                try:
                    detections = self._detect_and_track(frame)
                    last_detections = detections
                    events = self.gate_counter.update(detections)
                    for event in events:
                        self.last_count_at = datetime.now(timezone.utc)
                        self.on_crossing(self.venue_id, self.gate_id, event)
                except Exception as e:
                    logger.error(f"Detection error (gate {self.gate_id}): {e}")

            # 3. Encode stream JPEG at 5 FPS max (every 200ms)
            if (now - last_encode_time >= 0.1):
                try:
                    small = self._resize_for_stream(frame)
                    annotated = self._annotate_frame_fast(small, last_detections)
                    success, buf = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 45])
                    if success:
                        with self._frame_lock:
                            self._latest_jpeg = buf.tobytes()
                        last_encode_time = now
                except Exception as e:
                    logger.debug(f"Frame encoding error: {e}")

            time.sleep(0.02)

    def _resize_for_stream(self, frame: np.ndarray) -> np.ndarray:
        """Downscale frame to max 480px width for lightweight tunnel streaming."""
        h, w = frame.shape[:2]
        if w > 480:
            scale = 480 / w
            return cv2.resize(frame, (480, int(h * scale)), interpolation=cv2.INTER_AREA)
        return frame

    def _annotate_frame_fast(self, frame: np.ndarray, detections: list[dict]) -> np.ndarray:
        """Lightweight annotation — baseline + head dots + count badge only. No heavy text overlays."""
        h, w = frame.shape[:2]
        cfg = self.gate_counter.config
        is_entry = (str(cfg.gate_type).upper().endswith("ENTRY") or cfg.gate_type == "ENTRY")
        is_counting = getattr(self.gate_counter, "counting_enabled", True)

        # Counting baseline
        lx1, ly1 = int(cfg.start_x * w), int(cfg.start_y * h)
        lx2, ly2 = int(cfg.end_x * w), int(cfg.end_y * h)

        line_color = (50, 220, 80) if is_entry else (60, 60, 240)
        if not is_counting:
            line_color = (0, 200, 255)
        cv2.line(frame, (lx1, ly1), (lx2, ly2), (15, 23, 42), 4)
        cv2.line(frame, (lx1, ly1), (lx2, ly2), line_color, 2)

        # Head detection dots
        for det in detections:
            hx = int(det.get("head_x", 0.0) * w)
            hy = int(det.get("head_y", 0.0) * h)
            status = det.get("status", "")
            if status == "ENTRY EVENT":
                color = (50, 240, 80)
            elif status == "EXIT EVENT":
                color = (255, 120, 40)
            else:
                color = (220, 220, 220)
            cv2.circle(frame, (hx, hy), 4, color, -1, cv2.LINE_AA)
            cv2.circle(frame, (hx, hy), 6, color, 1, cv2.LINE_AA)

        # Bottom count badge
        if is_counting:
            count_text = f"IN: {self.gate_counter.total_in}" if is_entry else f"OUT: {self.gate_counter.total_out}"
            badge_bg = (40, 180, 70) if is_entry else (50, 50, 220)
        else:
            count_text = "STANDBY"
            badge_bg = (30, 140, 220)
        cv2.rectangle(frame, (4, h - 22), (90, h - 2), badge_bg, -1)
        cv2.putText(frame, count_text, (8, h - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)

        return frame

    def _annotate_frame(self, frame: np.ndarray, detections: list[dict]) -> np.ndarray:
        """Annotate frame with high-visibility counting baseline, directional regions, pedestrian tracking, and debug HUD."""
        h, w = frame.shape[:2]
        cfg = self.gate_counter.config
        is_entry = (str(cfg.gate_type).upper().endswith("ENTRY") or cfg.gate_type == "ENTRY")
        is_counting = getattr(self.gate_counter, "counting_enabled", True)
        margin = getattr(cfg, "hysteresis_margin", 0.015)

        now = time.time()
        is_flashing = (now - self.gate_counter.last_flash_time < 0.6)

        # 1. Configured Counting Baseline & Hysteresis Deadband Corridor
        lx1, ly1 = int(cfg.start_x * w), int(cfg.start_y * h)
        lx2, ly2 = int(cfg.end_x * w), int(cfg.end_y * h)
        margin_px = int(margin * h)

        # Subtle deadband corridor boundary lines (hysteresis zone)
        deadband_upper_y = max(32, ly1 - margin_px)
        deadband_lower_y = min(h - 34, ly1 + margin_px)
        cv2.line(frame, (lx1, deadband_upper_y), (lx2, deadband_upper_y), (40, 60, 80), 1, cv2.LINE_AA)
        cv2.line(frame, (lx1, deadband_lower_y), (lx2, deadband_lower_y), (40, 60, 80), 1, cv2.LINE_AA)

        # Shadow background line for primary baseline
        cv2.line(frame, (lx1, ly1), (lx2, ly2), (15, 23, 42), 6)

        # Foreground baseline line color
        if not is_counting:
            line_color = (0, 200, 255)  # Calibration amber
            line_thickness = 4
        elif is_flashing:
            line_color = (0, 240, 255)  # Flash golden-amber
            line_thickness = 4
        else:
            line_color = (50, 220, 80) if is_entry else (60, 60, 240)
            line_thickness = 3

        cv2.line(frame, (lx1, ly1), (lx2, ly2), line_color, line_thickness)

        # Baseline center title banner
        mid_x = (lx1 + lx2) // 2
        mid_y = (ly1 + ly2) // 2
        gate_title = getattr(self, "gate_name", None) or f"GATE {self.gate_id[:8]}"
        if not is_counting:
            line_label = f"⚙ CALIBRATION: {gate_title.upper()} (COUNTING PAUSED)"
        else:
            line_label = f"BASELINE: {gate_title.upper()} (COUNTING ZONE: {'BELOW BASELINE' if is_entry else 'ABOVE BASELINE'})"

        (tw, th), _ = cv2.getTextSize(line_label, cv2.FONT_HERSHEY_SIMPLEX, 0.44, 1)
        bx1 = max(10, mid_x - tw // 2 - 8)
        by1 = max(10, mid_y - th - 7)
        bx2 = min(w - 10, mid_x + tw // 2 + 8)
        by2 = max(10, mid_y + 4)
        cv2.rectangle(frame, (bx1, by1), (bx2, by2), (15, 23, 42), -1)
        cv2.rectangle(frame, (bx1, by1), (bx2, by2), line_color, 1)
        cv2.putText(
            frame, line_label, (bx1 + 8, by1 + th + 3),
            cv2.FONT_HERSHEY_SIMPLEX, 0.44, (255, 255, 255), 1, cv2.LINE_AA
        )

        # 2. Regional Zone Badges (Upper Region ABOVE vs Lower Region BELOW)
        # Upper Region Badge
        upper_tag = "UPPER REGION [ABOVE] - APPROACH ZONE" if is_entry else "UPPER REGION [ABOVE] - TARGET EXIT ZONE"
        upper_bg = (30, 45, 60) if is_entry else (50, 30, 100)
        cv2.rectangle(frame, (12, 38), (12 + 300, 58), upper_bg, -1)
        cv2.putText(frame, upper_tag, (18, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (220, 230, 245), 1, cv2.LINE_AA)

        # Lower Region Badge
        lower_tag = "LOWER REGION [BELOW] - TARGET ENTRY ZONE" if is_entry else "LOWER REGION [BELOW] - APPROACH ZONE"
        lower_bg = (20, 60, 35) if is_entry else (30, 45, 60)
        cv2.rectangle(frame, (12, h - 56), (12 + 310, h - 36), lower_bg, -1)
        cv2.putText(frame, lower_tag, (18, h - 42), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (220, 245, 225), 1, cv2.LINE_AA)

        # 3. Head Detections, Reference Point, Trajectory, and Debug Badges
        # Strictly avoids full-body boxes; uses compact head rings, center focal points, and H-ID pills
        for det in detections:
            if "bbox" in det:
                bx1, by1, bx2, by2 = [int(v) for v in det["bbox"]]
                status = det.get("status", "TRACKING")
                region = det.get("region", "ON_LINE")
                is_blocked = det.get("is_blocked", False)
                track_id = det["track_id"]

                # Head center coordinates
                hx = int(det.get("head_x", det.get("person_x", 0.0)) * w)
                hy = int(det.get("head_y", det.get("person_y", 0.0)) * h)
                head_w = max(8, bx2 - bx1)
                head_h = max(8, by2 - by1)
                head_radius = max(5, min(head_w, head_h) // 2)

                # Determine color based on algorithm state
                if not is_counting:
                    color = (0, 200, 255)      # Amber for calibration
                    badge_status = region
                elif is_blocked:
                    color = (30, 30, 245)      # Red for anti-passback violation
                    badge_status = "BLOCKED"
                elif status == "ENTRY EVENT":
                    color = (50, 240, 80)      # Bright Green for entry
                    badge_status = "IN"
                elif status == "EXIT EVENT":
                    color = (255, 120, 40)     # Bright Coral/Orange for exit
                    badge_status = "OUT"
                elif region == "ABOVE":
                    color = (220, 180, 50)     # Sky Blue
                    badge_status = "ABOVE"
                elif region == "BELOW":
                    color = (80, 200, 120)     # Mint Green
                    badge_status = "BELOW"
                else:
                    color = (180, 180, 180)    # Gray for deadband ON_LINE
                    badge_status = "LINE"

                # 1. Trajectory trail: smooth trail of recent head centers
                track_state = self.gate_counter.tracks.get(track_id)
                if track_state and len(track_state.history) >= 2:
                    pts = [(int(pt[1] * w), int(pt[2] * h)) for pt in track_state.history[-8:]]
                    for idx in range(len(pts) - 1):
                        cv2.line(frame, pts[idx], pts[idx + 1], color, 1, cv2.LINE_AA)
                    # Direction indicator
                    if len(pts) >= 2:
                        p_prev = pts[-2]
                        p_curr = pts[-1]
                        if abs(p_curr[0] - p_prev[0]) > 1 or abs(p_curr[1] - p_prev[1]) > 1:
                            cv2.arrowedLine(frame, p_prev, p_curr, (255, 255, 255), 1, tipLength=0.35)

                # 2. Sleek Head Marker: Compact Head Boundary + Concentric Target Ring + Center Bullseye
                cv2.rectangle(frame, (bx1, by1), (bx2, by2), color, 1, cv2.LINE_AA)
                cv2.circle(frame, (hx, hy), head_radius + 2, color, 2, cv2.LINE_AA)
                cv2.circle(frame, (hx, hy), 3, (255, 255, 255), -1, cv2.LINE_AA)

                # 3. Compact Stable Tracking ID Pill: "H-{track_id}"
                if badge_status in ("IN", "OUT", "BLOCKED"):
                    id_text = f"H-{track_id} [{badge_status}]"
                else:
                    id_text = f"H-{track_id}"

                (tw, th), _ = cv2.getTextSize(id_text, cv2.FONT_HERSHEY_SIMPLEX, 0.36, 1)
                tag_x1 = max(4, hx - tw // 2 - 4)
                tag_y1 = max(34, by1 - th - 5)
                tag_x2 = min(w - 4, tag_x1 + tw + 8)
                tag_y2 = tag_y1 + th + 4

                cv2.rectangle(frame, (tag_x1, tag_y1), (tag_x2, tag_y2), (15, 23, 42), -1)
                cv2.rectangle(frame, (tag_x1, tag_y1), (tag_x2, tag_y2), color, 1)
                cv2.putText(
                    frame, id_text, (tag_x1 + 4, tag_y1 + th + 1),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.36, (255, 255, 255), 1, cv2.LINE_AA
                )

        # 4. Top Surveillance Header
        cv2.rectangle(frame, (0, 0), (w, 30), (15, 23, 42), -1)
        mode_tag = "LIVE COUNTING" if is_counting else "CALIBRATION / SETUP"
        top_left = f"AI SURVEILLANCE  |  {gate_title.upper()}  |  {mode_tag}"
        cv2.putText(frame, top_left, (12, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (240, 245, 255), 1, cv2.LINE_AA)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        (tw, _), _ = cv2.getTextSize(ts, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
        cv2.putText(frame, ts, (w - tw - 12, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200, 215, 235), 1, cv2.LINE_AA)

        # 5. Bottom HUD Footer
        cv2.rectangle(frame, (0, h - 32), (w, h), (15, 23, 42), -1)
        if not is_counting:
            badge_text = "STANDBY"
            badge_bg = (30, 140, 220)  # Amber
            cv2.rectangle(frame, (8, h - 26), (105, h - 6), badge_bg, -1)
            cv2.putText(frame, badge_text, (16, h - 11), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
            status_msg = "CALIBRATION MODE: ADJUST LINE BELOW & CLICK [START PROCESS]"
            cv2.putText(frame, status_msg, (120, h - 11), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 220, 255), 1, cv2.LINE_AA)
        else:
            badge_text = f"IN: {self.gate_counter.total_in}" if is_entry else f"OUT: {self.gate_counter.total_out}"
            badge_bg = (40, 180, 70) if is_entry else (50, 50, 220)
            cv2.rectangle(frame, (8, h - 26), (110, h - 6), badge_bg, -1)
            cv2.putText(frame, badge_text, (16, h - 11), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
            status_msg = "LIVE COUNTING ACTIVE  |  HEAD-BASED PERSISTENT TRACKING"
            violations_count = len(self.gate_counter.blocked_violations)
            if violations_count > 0:
                status_msg += f"  |  {violations_count} VIOLATIONS BLOCKED"
            cv2.putText(frame, status_msg, (125, h - 11), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (160, 185, 215), 1, cv2.LINE_AA)

        return frame

    def _detect_and_track(self, frame: np.ndarray) -> list[dict]:
        """Run head detection with persistent tracking and return normalized head-center reference points."""
        h, w = frame.shape[:2]

        is_head_model = getattr(self, "_is_head_model", True)
        track_kwargs = {
            "persist": True,
            "conf": self.confidence,
            "iou": settings.YOLO_IOU_THRESHOLD,
            "imgsz": self.imgsz,
            "tracker": self.tracker_config,
            "verbose": False,
        }
        if not is_head_model:
            track_kwargs["classes"] = [0]

        results = self.model.track(frame, **track_kwargs)

        detections = []
        if results and len(results) > 0:
            result = results[0]
            if result.boxes is not None and result.boxes.id is not None:
                boxes = result.boxes
                for i in range(len(boxes)):
                    track_id = int(boxes.id[i].item())
                    x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                    conf = boxes.conf[i].item()

                    # Primary tracking reference: Head Center Point
                    # head_x = (x1 + x2) / 2
                    # head_y = (y1 + y2) / 2
                    head_x = ((x1 + x2) / 2.0) / w
                    head_y = ((y1 + y2) / 2.0) / h

                    detections.append({
                        "track_id": track_id,
                        "head_x": head_x,
                        "head_y": head_y,
                        "person_x": head_x,  # for gate counter compatibility
                        "person_y": head_y,  # for gate counter compatibility
                        "cx": head_x,
                        "cy": head_y,
                        "feet_y": head_y,
                        "top_y": y1 / h,
                        "confidence": conf,
                        "bbox": [x1, y1, x2, y2],
                    })

        return detections

    def _reconnect_backoff(self):
        """Wait with bounded exponential backoff before reconnecting."""
        self.reconnect_attempts += 1
        if self.reconnect_attempts >= 3:
            self._set_status(GateStatus.ERROR, self.error_message or "Max reconnection attempts exceeded")
        if self.reconnect_attempts > settings.CAMERA_RECONNECT_MAX_ATTEMPTS:
            self._set_status(GateStatus.ERROR, self.error_message or "Max reconnection attempts exceeded")
            self._stop_event.set()
            return

        delay = min(
            settings.CAMERA_RECONNECT_BASE_DELAY * (2 ** (self.reconnect_attempts - 1)),
            settings.CAMERA_RECONNECT_MAX_DELAY,
        )
        logger.info(f"Reconnecting gate {self.gate_id} in {delay:.0f}s (attempt {self.reconnect_attempts})")
        self._stop_event.wait(delay)

    def _release_capture(self):
        """Release OpenCV capture."""
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def _set_status(self, status: GateStatus, error: str | None = None):
        """Update status and notify."""
        self.status = status
        if error:
            self.error_message = error
        self.on_status_change(self.gate_id, status.value, error)

    def get_health(self) -> dict:
        """Return current health info."""
        return {
            "gate_id": self.gate_id,
            "status": self.status.value,
            "last_frame_at": self.last_frame_at.isoformat() if self.last_frame_at else None,
            "last_count_at": self.last_count_at.isoformat() if self.last_count_at else None,
            "frames_processed": self.frames_processed,
            "reconnect_attempts": self.reconnect_attempts,
            "error_message": self.error_message,
            "counts": self.gate_counter.get_counts(),
        }

    def get_latest_frame(self) -> Optional[bytes]:
        """Return latest encoded JPEG frame bytes."""
        with self._frame_lock:
            return self._latest_jpeg



class CameraManager:
    """
    Manages multiple CameraWorker instances.

    Provides lifecycle management, model sharing, and health aggregation.
    """

    def __init__(self):
        self._workers: dict[str, CameraWorker] = {}
        self._model = None
        self._model_lock = threading.Lock()
        self._crossing_callbacks: list[Callable] = []
        self._status_callbacks: list[Callable] = []
        self._model_pool: list = []
        self._pool_lock = threading.Lock()
        self._is_preloading = False

    @staticmethod
    def _resolve_model_path() -> str:
        from pathlib import Path
        service_dir = Path(__file__).resolve().parent
        cand_names = ["yolo11s.pt", "11s-head.pt", "11n-head.pt"]
        cand_dirs = [
            service_dir.parent.parent,
            service_dir.parent.parent.parent / "fastreid",
            service_dir.parent.parent.parent,
            Path(os.getcwd()) / "backend",
            Path(os.getcwd()),
        ]
        for cdir in cand_dirs:
            for cname in cand_names:
                cand = cdir / cname
                if cand.exists():
                    return str(cand)
        return "yolo11s.pt"

    def preload_models(self, count: int = 4):
        """Preload YOLO model instances into memory so camera startup is instantaneous (0s)."""
        if self._is_preloading:
            return
        self._is_preloading = True

        def _do_preload():
            try:
                from ultralytics import YOLO
                m_path = self._resolve_model_path()
                logger.info(f"Pre-warming YOLO model pool ({count} workers) from {m_path}...")
                for i in range(count):
                    try:
                        m = YOLO(m_path)
                        with self._pool_lock:
                            self._model_pool.append(m)
                            if self._model is None:
                                self._model = m
                    except Exception as e:
                        logger.warning(f"Error preloading model instance {i}: {e}")
                logger.info(f"YOLO model pool successfully pre-warmed with {len(self._model_pool)} instances!")
            except Exception as e:
                logger.error(f"YOLO preload failed: {e}")
            finally:
                self._is_preloading = False

        threading.Thread(target=_do_preload, daemon=True, name="yolo-preloader").start()

    def get_pooled_model(self):
        """Get an already-loaded model instance from the pre-warmed pool in 0ms."""
        with self._pool_lock:
            if self._model_pool:
                return self._model_pool.pop(0)
            if self._model is not None:
                return self._model
        return self.create_worker_model()

    @staticmethod
    def create_worker_model():
        """Instantiate an independent YOLO model to ensure dedicated tracker state per camera worker."""
        try:
            from ultralytics import YOLO
            import os
            from pathlib import Path

            # Prioritize dedicated head-based detection model when enabled
            use_head = getattr(settings, "USE_HEAD_TRACKING", True)
            model_path = settings.HEAD_MODEL_PATH if use_head else settings.YOLO_MODEL_PATH

            if not os.path.exists(model_path):
                # Search candidate locations relative to this file
                service_dir = Path(__file__).resolve().parent
                cand_names = ["11s-head.pt", "11n-head.pt", "yolo11s.pt"] if use_head else ["yolo11s.pt"]
                cand_dirs = [
                    service_dir.parent.parent,
                    service_dir.parent.parent.parent,
                    Path(os.getcwd()) / "backend",
                    Path(os.getcwd()),
                ]
                for cdir in cand_dirs:
                    for cname in cand_names:
                        cand = cdir / cname
                        if cand.exists():
                            model_path = str(cand)
                            break
                    if os.path.exists(model_path):
                        break

            logger.info(f"Loading independent YOLO model instance: {model_path} (head_tracking={use_head})")
            with _model_init_lock:
                model = YOLO(model_path)
            device = settings.resolved_yolo_device
            logger.info(f"YOLO worker device: {device}")
            return model
        except Exception as e:
            logger.error(f"Failed to load isolated YOLO model: {e}")
            return None

    def _get_model(self):
        """Lazy-load YOLO model (fallback / backward compatibility)."""
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    self._model = self.create_worker_model()
        return self._model

    def on_crossing(self, callback: Callable):
        """Register a callback for crossing events."""
        self._crossing_callbacks.append(callback)

    def on_status_change(self, callback: Callable):
        """Register a callback for status changes."""
        self._status_callbacks.append(callback)

    def _handle_crossing(self, venue_id: str, gate_id: str, event: CrossingEvent):
        """Forward crossing events to all registered callbacks."""
        for cb in self._crossing_callbacks:
            try:
                cb(venue_id, gate_id, event)
            except Exception as e:
                logger.error(f"Crossing callback error: {e}")

    def _handle_status_change(self, gate_id: str, status: str, error: str | None):
        """Forward status changes to all registered callbacks."""
        for cb in self._status_callbacks:
            try:
                cb(gate_id, status, error)
            except Exception as e:
                logger.error(f"Status callback error: {e}")

    def start_gate(
        self,
        gate_id: str,
        venue_id: str,
        camera_source: str | int,
        line_config: LineCrossingConfig,
        confidence: float = 0.25,
        imgsz: int = 640,
        frame_skip: int = 1,
        gate_name: str = "",
        counting_enabled: bool = True,
    ) -> bool:
        """Start processing for a gate."""
        if gate_id in self._workers:
            logger.warning(f"Worker already running for gate {gate_id}")
            return False

        # Pass model if already loaded, or model_getter for lazy loading in thread
        model = self._model
        counter = GateCounter(line_config, counting_enabled=counting_enabled)

        # Determine tracker config path
        import os
        tracker_dir = os.path.join(os.path.dirname(__file__), "..", "..", "tracker_configs")
        tracker_file = "botsort.yaml" if settings.TRACKER_TYPE == "botsort" else "bytetrack.yaml"
        tracker_path = os.path.join(tracker_dir, tracker_file)
        if not os.path.exists(tracker_path):
            tracker_path = tracker_file  # Fall back to ultralytics default

        worker = CameraWorker(
            gate_id=gate_id,
            venue_id=venue_id,
            camera_source=camera_source,
            gate_counter=counter,
            on_crossing=self._handle_crossing,
            on_status_change=self._handle_status_change,
            model=None,
            model_getter=self.get_pooled_model,
            confidence=confidence,
            imgsz=imgsz,
            frame_skip=frame_skip,
            tracker_config=tracker_path,
            gate_name=gate_name,
        )

        self._workers[gate_id] = worker
        worker.start()
        return True

    def update_gate_line(
        self,
        gate_id: str,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        counting_direction: str | None = None,
    ) -> bool:
        """Update counting line parameters on a running camera worker instantly."""
        worker = self._workers.get(gate_id)
        if worker:
            cfg = worker.gate_counter.config
            cfg.start_x = start_x
            cfg.start_y = start_y
            cfg.end_x = end_x
            cfg.end_y = end_y
            if counting_direction:
                cfg.counting_direction = counting_direction
            worker.gate_counter._update_line_vector()
            return True
        return False

    def stop_gate(self, gate_id: str) -> bool:
        """Stop processing for a gate."""
        worker = self._workers.pop(gate_id, None)
        if worker:
            worker.stop()
            return True
        return False

    def stop_all(self):
        """Stop all camera workers."""
        for gate_id in list(self._workers.keys()):
            self.stop_gate(gate_id)

    def get_health(self, gate_id: str = None) -> dict | list:
        """Get health for one or all workers."""
        if gate_id:
            worker = self._workers.get(gate_id)
            return worker.get_health() if worker else None
        return [w.get_health() for w in self._workers.values()]

    def is_running(self, gate_id: str) -> bool:
        """Check if a gate worker is running."""
        return gate_id in self._workers

    @property
    def active_count(self) -> int:
        return len(self._workers)

    def set_venue_counting(self, venue_id: str, enabled: bool):
        """Enable or disable counting on all camera workers for a venue."""
        for worker in self._workers.values():
            if worker.venue_id == venue_id:
                worker.gate_counter.counting_enabled = enabled
                logger.info(f"Gate {worker.gate_id} counting set to {enabled}")

    def reset_venue_counters(self, venue_id: str):
        """Reset counts and tracking state on all camera workers for a venue."""
        for worker in self._workers.values():
            if worker.venue_id == venue_id:
                worker.gate_counter.reset()
                logger.info(f"Gate {worker.gate_id} counter reset to 0")

    def is_venue_counting(self, venue_id: str) -> bool:
        """Check if counting is currently active for a venue."""
        workers = [w for w in self._workers.values() if w.venue_id == venue_id]
        if not workers:
            return False
        return any(w.gate_counter.counting_enabled for w in workers)

    def get_latest_frame(self, gate_id: str) -> Optional[bytes]:
        """Get latest frame JPEG bytes for a gate."""
        worker = self._workers.get(gate_id)
        return worker.get_latest_frame() if worker else None



# Global singleton
camera_manager = CameraManager()
