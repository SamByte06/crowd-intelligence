import os
import re
import threading
import time
import cv2

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


def is_youtube_url(source):
    if not isinstance(source, str):
        return False
    source = source.strip()
    return bool(
        re.search(r"(?:https?://)?(?:www\.)?(?:youtube\.com|youtu\.be)/", source, re.IGNORECASE)
    )


def extract_youtube_info(youtube_url):
    """
    Extract direct stream URL, video title, live status, and FPS from a YouTube link using yt-dlp.
    Uses multi-client extraction (android, ios, web) to bypass YouTube bot detection challenges.
    """
    if yt_dlp is None:
        raise RuntimeError("yt-dlp is not installed. Run: pip install yt-dlp")

    ydl_opts = {
        # Prefer MP4 video <= 720p for fast decoding, low network buffering, and smooth AI inference
        "format": "bestvideo[ext=mp4][height<=720]/bestvideo[height<=720]/best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "noplaylist": True,
        # Multi-client fallback: Android and iOS client APIs bypass bot challenges that block desktop web
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "web"]
            }
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url.strip(), download=False)
            if not info:
                raise ValueError("Could not retrieve video information from YouTube.")

            stream_url = info.get("url")
            if not stream_url:
                req_formats = info.get("requested_formats")
                if req_formats and len(req_formats) > 0:
                    stream_url = req_formats[0].get("url")

            if not stream_url:
                raise ValueError("No direct video stream URL found for this YouTube link.")

            title = info.get("title", "YouTube Video")
            is_live = bool(info.get("is_live") or (info.get("live_status") == "is_live"))
            fps = info.get("fps") or 30.0

            return {
                "stream_url": stream_url,
                "title": title,
                "is_live": is_live,
                "fps": float(fps) if fps else 30.0,
                "duration": info.get("duration"),
            }
    except Exception as e:
        raw_msg = str(e)
        # Strip all ANSI color escape sequences and raw terminal formatting
        clean_msg = re.sub(r"\x1b\[[0-9;]*m", "", raw_msg)
        clean_msg = re.sub(r"\[\[0;[0-9]+m[^\]]*\]", "", clean_msg)
        clean_msg = clean_msg.replace("[0m", "").replace("[youtube]", "").strip()

        if "Sign in to confirm you're not a bot" in clean_msg or "bot" in clean_msg.lower():
            friendly_err = "YouTube Bot Verification: YouTube requires sign-in for this video. Please try another YouTube URL, a Quick Test Preset below, or switch to Webcam."
        elif "Private video" in clean_msg or "Video unavailable" in clean_msg:
            friendly_err = "Video Unavailable: This video is private, restricted, or removed on YouTube."
        else:
            friendly_err = f"Failed to load YouTube stream: {clean_msg[:140]}"

        raise RuntimeError(friendly_err)


class UniversalCapture:
    """
    Thread-safe video capture manager supporting:
    - Webcams (0, 1, 2...)
    - YouTube URLs (via yt-dlp direct video stream)
    - Video files (e.g. crowd_test.mp4)
    - Network streams (RTSP / HTTP)
    Features real-time pacing for pre-recorded videos, auto-looping for continuous AI testing,
    and dynamic live source switching.
    """

    def __init__(self, source=0):
        self.raw_source = source
        self.source_type = "webcam"  # 'webcam', 'youtube', 'file', 'stream'
        self.display_name = "Camera 01 - Main Entrance"
        self.video_title = None
        self.actual_stream_url = None
        self.is_live = True
        self.fps = 30.0
        self.is_mirror = True  # Only mirror for local webcam

        self.capture = None
        self.frame = None
        self.lock = threading.Lock()
        self.running = False
        self._thread = None
        self.last_error = None

    def start(self):
        self.running = True
        self._init_source(self.raw_source)
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        return self

    def _init_source(self, source):
        with self.lock:
            if self.capture is not None:
                try:
                    self.capture.release()
                except Exception:
                    pass
                self.capture = None

            self.raw_source = source
            self.last_error = None

            # 1. Check if source is a YouTube URL
            if is_youtube_url(source):
                try:
                    print(f"[AI Video Engine] Resolving YouTube link: {source}")
                    info = extract_youtube_info(source)
                    self.actual_stream_url = info["stream_url"]
                    self.video_title = info["title"]
                    self.is_live = info["is_live"]
                    self.fps = max(10.0, min(float(info.get("fps") or 30.0), 60.0))
                    self.source_type = "youtube"
                    self.is_mirror = False
                    self.display_name = f"YouTube: {self.video_title[:32]}"
                    print(f"[AI Video Engine] YouTube stream loaded: '{self.video_title}' (Live={self.is_live}, FPS={self.fps})")
                    self.capture = cv2.VideoCapture(self.actual_stream_url)
                except Exception as err:
                    self.last_error = str(err)
                    print(f"[AI Video Engine] Error loading YouTube video: {err}")
                    raise

            # 2. Check if source is integer or string digit (webcam)
            elif isinstance(source, int) or (isinstance(source, str) and source.strip().isdigit()):
                idx = int(source)
                self.source_type = "webcam"
                self.display_name = f"Laptop Webcam {idx}"
                self.video_title = f"Webcam Device {idx}"
                self.actual_stream_url = idx
                self.is_live = True
                self.is_mirror = True
                self.fps = 30.0
                print(f"[AI Video Engine] Opening Webcam Index {idx}...")
                self.capture = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if self.capture.isOpened():
                    self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            # 3. Local file or other network stream
            else:
                src_str = str(source).strip()
                self.actual_stream_url = src_str
                self.is_mirror = False
                if os.path.exists(src_str):
                    self.source_type = "file"
                    self.display_name = f"File: {os.path.basename(src_str)}"
                    self.video_title = os.path.basename(src_str)
                    self.is_live = False
                else:
                    self.source_type = "stream"
                    self.display_name = "Network Stream"
                    self.video_title = src_str
                    self.is_live = True

                print(f"[AI Video Engine] Opening source: {src_str}...")
                self.capture = cv2.VideoCapture(src_str)
                fps_detected = self.capture.get(cv2.CAP_PROP_FPS)
                if fps_detected and fps_detected > 5:
                    self.fps = float(fps_detected)
                else:
                    self.fps = 30.0

            if not self.capture or not self.capture.isOpened():
                raise RuntimeError(f"Could not open video source: {source}")

    def change_source(self, new_source):
        """
        Dynamically switches video feed to new source (YouTube URL, webcam index, or file).
        """
        print(f"[AI Video Engine] Switching source to: {new_source}")
        try:
            self._init_source(new_source)
            return True, f"Successfully switched to {self.display_name}"
        except Exception as e:
            return False, str(e)

    def _read_loop(self):
        target_frame_interval = 1.0 / self.fps if self.fps > 0 else 0.033
        last_frame_time = time.time()

        while self.running:
            with self.lock:
                cap = self.capture

            if cap is None or not cap.isOpened():
                time.sleep(0.05)
                continue

            # Frame pacing for pre-recorded YouTube videos or files
            if not self.is_live and self.fps > 0:
                elapsed = time.time() - last_frame_time
                wait_time = (1.0 / self.fps) - elapsed
                if wait_time > 0.001:
                    time.sleep(min(wait_time, 0.05))
                last_frame_time = time.time()

            try:
                ok, frame = cap.read()
            except Exception:
                time.sleep(0.05)
                continue

            if not ok:
                # Video ended or temporary buffer underflow
                if not self.is_live:
                    # Automatically loop back to start for testing
                    try:
                        self.capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ok_rewind, frame_rewind = self.capture.read()
                        if ok_rewind and frame_rewind is not None:
                            frame = frame_rewind
                            ok = True
                        else:
                            # Re-open capture if seek is not supported over network stream
                            self.capture.release()
                            self.capture = cv2.VideoCapture(self.actual_stream_url)
                    except Exception:
                        time.sleep(0.1)
                        continue
                else:
                    time.sleep(0.02)
                    continue

            if frame is None:
                time.sleep(0.01)
                continue

            # Mirror webcam only
            if self.is_mirror:
                frame = cv2.flip(frame, 1)

            with self.lock:
                self.frame = frame

    def read(self):
        with self.lock:
            if self.frame is None:
                return None
            return self.frame.copy()

    def get_info(self):
        with self.lock:
            return {
                "source": str(self.raw_source),
                "source_type": self.source_type,
                "display_name": self.display_name,
                "video_title": self.video_title,
                "is_live": self.is_live,
                "fps": round(self.fps, 1),
                "is_opened": self.capture is not None and self.capture.isOpened(),
                "last_error": self.last_error,
            }

    def stop(self):
        self.running = False
        with self.lock:
            if self.capture is not None:
                try:
                    self.capture.release()
                except Exception:
                    pass
                self.capture = None
