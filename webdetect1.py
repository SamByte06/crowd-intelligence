import cv2
import numpy as np
import time
import threading
from ultralytics import YOLO

CAMERA_INDEX = 0
MODEL_PATH = "yolo11s.pt"

CONFIDENCE = 0.28
IMAGE_SIZE = 640
DEVICE = 0

# ── Classification Thresholds ──
REAL_THRESHOLD_HIGH = 0.50   # Threshold to become REAL
REAL_THRESHOLD_LOW  = 0.42   # Threshold to drop to FILTERED (Hysteresis)
MIN_BBOX_AREA_RATIO = 0.005  # Minimum relative area in frame

# COCO class IDs
PERSON_CLASS = 0
SCREEN_CLASSES = {62, 63, 67}       # tv, laptop, cell phone
DETECT_CLASSES = [0, 62, 63, 67]   # detect persons + screen devices


class TrackedPersonState:
    """Maintains smoothed temporal state for each tracked person."""
    def __init__(self, track_id, initial_score, initial_reason):
        self.track_id = track_id
        self.smoothed_score = initial_score
        self.is_real = (initial_score >= REAL_THRESHOLD_HIGH)
        self.primary_reason = initial_reason
        self.frame_count = 1

    def update(self, raw_score, reason, is_rigid_motion):
        self.frame_count += 1

        # Apply motion evidence
        if is_rigid_motion is True:
            raw_score = min(raw_score, 0.20)
            reason = "RIGID_2D_PHOTO"
        elif is_rigid_motion is False:
            raw_score = min(1.0, max(raw_score, 0.85))

        # Temporal EMA smoothing
        alpha = 0.35 if self.frame_count < 8 else 0.20
        self.smoothed_score = (1.0 - alpha) * self.smoothed_score + alpha * raw_score

        # Hysteresis switching
        if self.is_real:
            if self.smoothed_score < REAL_THRESHOLD_LOW:
                self.is_real = False
        else:
            if self.smoothed_score >= REAL_THRESHOLD_HIGH:
                self.is_real = True

        self.primary_reason = reason


class RealPersonFilter:
    """
    Advanced Multi-Signal Real Person vs Screen/Photo Filter.
    
    1. YOLO Screen Device Overlap Check (Direct Phone / Screen detection)
    2. Spatial Nesting Check (Phone person held inside real person body)
    3. Bezel & Dark Casing Edge Detection
    4. Glass Specular Glare & Backlight Check
    5. Screen Portrait Aspect Ratio Check (h:w ~ 1.7 to 2.5)
    6. Optical Flow 2D Planar Rigidity Analysis (Rigid photo vs 3D human)
    7. Track-based Hysteresis State Machine (Zero fumbling)
    """

    def __init__(self):
        self.frame_area = 1
        self.frame_h = 1
        self.frame_w = 1
        self.track_states = {}
        self.prev_frame_gray = None

    def update_frame(self, frame):
        self.frame_h, self.frame_w = frame.shape[:2]
        self.frame_area = max(1, self.frame_h * self.frame_w)

    def _clamp_crop(self, frame, x1, y1, x2, y2):
        h, w = frame.shape[:2]
        x1, y1 = max(0, int(x1)), max(0, int(y1))
        x2, y2 = min(w, int(x2)), min(h, int(y2))
        if x2 <= x1 or y2 <= y1:
            return None
        crop = frame[y1:y2, x1:x2]
        return crop if crop.size > 0 else None

    # ── Screen Device Overlap Check ──
    def _check_screen_overlap(self, box, screen_boxes):
        if len(screen_boxes) == 0:
            return False, 1.0

        x1, y1, x2, y2 = box
        p_area = max(1, (x2 - x1) * (y2 - y1))

        for sbox in screen_boxes:
            sx1, sy1, sx2, sy2 = sbox
            s_area = max(1, (sx2 - sx1) * (sy2 - sy1))
            
            # Pad screen box slightly
            pw = (sx2 - sx1) * 0.12
            ph = (sy2 - sy1) * 0.12
            esx1, esy1 = sx1 - pw, sy1 - ph
            esx2, esy2 = sx2 + pw, sy2 + ph

            ix1, iy1 = max(x1, esx1), max(y1, esy1)
            ix2, iy2 = min(x2, esx2), min(y2, esy2)

            if ix1 < ix2 and iy1 < iy2:
                inter = (ix2 - ix1) * (iy2 - iy1)
                overlap_person = inter / p_area
                # Person is on a screen if mostly inside screen, AND person area is not massive compared to screen
                if overlap_person > 0.40 and p_area < (s_area * 1.6):
                    return True, 0.05

        return False, 1.0

    # ── Nesting Check ──
    def _check_nesting(self, box, all_boxes, idx):
        x1, y1, x2, y2 = box
        box_area = (x2 - x1) * (y2 - y1)
        if box_area <= 0:
            return False

        for i, other in enumerate(all_boxes):
            if i == idx:
                continue
            ox1, oy1, ox2, oy2 = other
            other_area = (ox2 - ox1) * (oy2 - oy1)
            ix1, iy1 = max(x1, ox1), max(y1, oy1)
            ix2, iy2 = min(x2, ox2), min(y2, oy2)
            if ix1 < ix2 and iy1 < iy2:
                inter_area = (ix2 - ix1) * (iy2 - iy1)
                overlap = inter_area / box_area
                if overlap > 0.50 and other_area > (box_area * 1.5):
                    return True
        return False

    # ── Bezel & Phone Border Check ──
    def _score_bezel(self, frame, box, area_ratio):
        # A large primary person taking >35% frame is real human body, not a bezel
        if area_ratio > 0.35:
            return 0.90

        h, w = frame.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in box]
        bw, bh = x2 - x1, y2 - y1
        if bw < 14 or bh < 14:
            return 0.50

        pad_x = max(3, int(bw * 0.08))
        pad_y = max(3, int(bh * 0.08))

        ex1, ey1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
        ex2, ey2 = min(w, x2 + pad_x), min(h, y2 + pad_y)

        roi = frame[ey1:ey2, ex1:ex2]
        if roi.size == 0:
            return 0.50

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        rw, rh = roi.shape[1], roi.shape[0]

        left_strip = gray[:, :max(2, int(rw * 0.08))]
        right_strip = gray[:, -max(2, int(rw * 0.08)):]
        top_strip = gray[:max(2, int(rh * 0.08)), :]

        dark_count = 0
        if np.mean(left_strip) < 65 or np.std(left_strip) < 25:
            dark_count += 1
        if np.mean(right_strip) < 65 or np.std(right_strip) < 25:
            dark_count += 1
        if np.mean(top_strip) < 65 or np.std(top_strip) < 25:
            dark_count += 1

        if dark_count >= 2:
            return 0.15
        elif dark_count == 1:
            return 0.40
        return 0.85

    # ── Glare & Aspect Ratio Check ──
    def _score_glare_and_ar(self, crop, box, area_ratio):
        h, w = crop.shape[:2]
        x1, y1, x2, y2 = box
        bw, bh = max(1, x2 - x1), max(1, y2 - y1)
        ratio = bh / bw

        is_phone_aspect = (1.60 <= ratio <= 2.60) and (area_ratio < 0.40)

        glare_mask = (crop[:, :, 0] > 220) & (crop[:, :, 1] > 220) & (crop[:, :, 2] > 220)
        glare_ratio = np.count_nonzero(glare_mask) / max(1, h * w)
 
        if is_phone_aspect and glare_ratio > 0.010:
            return 0.15, "PHONE_SCREEN"
        elif is_phone_aspect:
            return 0.35, "PHONE_ASPECT"
        elif glare_ratio > 0.025:
            return 0.30, "SCREEN_GLARE"
        return 0.85, "OK"

    # ── Optical Flow Rigidity ──
    def _analyze_rigidity(self, frame_gray, prev_gray, box):
        if prev_gray is None:
            return None

        x1, y1, x2, y2 = [int(v) for v in box]
        bw, bh = x2 - x1, y2 - y1
        if bw < 25 or bh < 25:
            return None

        crop_prev = prev_gray[y1:y2, x1:x2]
        crop_curr = frame_gray[y1:y2, x1:x2]
        if crop_prev.size == 0 or crop_curr.size == 0:
            return None

        pts = cv2.goodFeaturesToTrack(crop_prev, maxCorners=30, qualityLevel=0.03, minDistance=6)
        if pts is None or len(pts) < 6:
            return None

        pts_next, status, _ = cv2.calcOpticalFlowPyrLK(crop_prev, crop_curr, pts, None)
        if pts_next is None or status is None:
            return None

        valid = status.ravel() == 1
        pts_valid_prev = pts[valid].reshape(-1, 2)
        pts_valid_curr = pts_next[valid].reshape(-1, 2)

        if len(pts_valid_prev) < 6:
            return None

        motion_vectors = pts_valid_curr - pts_valid_prev
        mean_motion = np.mean(np.linalg.norm(motion_vectors, axis=1))

        if mean_motion > 0.7:
            affine, _ = cv2.estimateAffinePartial2D(pts_valid_prev, pts_valid_curr)
            if affine is not None:
                pts_trans = cv2.transform(pts_valid_prev.reshape(-1, 1, 2), affine).reshape(-1, 2)
                residual = float(np.mean(np.linalg.norm(pts_valid_curr - pts_trans, axis=1)))
                if residual < 0.18:
                    return True   # Rigid 2D motion (Phone / Photo)
                elif residual > 0.60:
                    return False  # Non-rigid 3D motion (Real Human)

        return None

    # ── Main Filter Evaluation ──
    def evaluate_person(self, frame, frame_gray, box, track_id, conf,
                        all_person_boxes, idx, screen_boxes):
        x1, y1, x2, y2 = box
        bw, bh = x2 - x1, y2 - y1
        area_ratio = (bw * bh) / self.frame_area

        # 1. Minimum area check
        if area_ratio < MIN_BBOX_AREA_RATIO:
            return 0.0, "TOO_SMALL", False

        # 2. YOLO Screen Device Overlap
        is_on_screen, s_overlap = self._check_screen_overlap(box, screen_boxes)
        if is_on_screen:
            raw_score = 0.05
            reason = "ON_SCREEN"
        # 3. Nesting inside another person
        elif self._check_nesting(box, all_person_boxes, idx):
            raw_score = 0.05
            reason = "NESTED"
        else:
            crop = self._clamp_crop(frame, x1, y1, x2, y2)
            if crop is None:
                return 0.0, "NO_CROP", False

            s_bezel = self._score_bezel(frame, box, area_ratio)
            s_glare_ar, glare_reason = self._score_glare_and_ar(crop, box, area_ratio)

            # Weight signals
            if area_ratio > 0.30:
                # Primary large person in frame
                raw_score = 0.90
                reason = "REAL"
            elif s_bezel < 0.20 or s_glare_ar < 0.20:
                raw_score = min(s_bezel, s_glare_ar)
                reason = glare_reason if s_glare_ar < 0.20 else "PHONE_BEZEL"
            else:
                raw_score = 0.50 * s_bezel + 0.35 * s_glare_ar + 0.15 * (1.0 if conf > 0.65 else 0.70)
                reason = "OK"

        # Optical Flow Rigidity
        is_rigid = self._analyze_rigidity(frame_gray, self.prev_frame_gray, box)

        # Track State Update
        if track_id not in self.track_states:
            self.track_states[track_id] = TrackedPersonState(track_id, raw_score, reason)
        tstate = self.track_states[track_id]
        tstate.update(raw_score, reason, is_rigid)

        return tstate.smoothed_score, tstate.primary_reason, tstate.is_real

    def post_frame_update(self, frame_gray, active_track_ids):
        self.prev_frame_gray = frame_gray.copy()
        stale_ids = [tid for tid in self.track_states if tid not in active_track_ids]
        for tid in stale_ids:
            if self.track_states[tid].frame_count > 60:
                del self.track_states[tid]


# ── Camera stream (threaded) ──
class CameraStream:
    def __init__(self, camera_index):
        self.cap = cv2.VideoCapture(camera_index)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.lock = threading.Lock()
        self.frame = None
        self.running = True

        self.thread = threading.Thread(
            target=self.update,
            daemon=True
        )
        self.thread.start()

    def update(self):
        while self.running:
            success, frame = self.cap.read()
            if success:
                with self.lock:
                    self.frame = frame
            else:
                time.sleep(0.01)

    def read(self):
        with self.lock:
            if self.frame is None:
                return False, None
            return True, self.frame.copy()

    def stop(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=1)
        self.cap.release()


# ── Initialization ──
camera = CameraStream(CAMERA_INDEX)

print("Loading YOLO11s...")
model = YOLO(MODEL_PATH)
print("YOLO11s loaded.")
print("Using GPU Device:", DEVICE)

person_filter = RealPersonFilter()

fps_counter = 0
fps_timer = time.time()
fps = 0

track_history = {}
MAX_HISTORY = 30

COLOR_REAL       = (0, 255, 0)     # Vibrant Green  — Real Person
COLOR_FILTERED   = (0, 0, 255)     # Bright Red     — Screen / Photo Person
COLOR_SCREEN_BOX = (255, 230, 0)   # Cyan / Gold    — Screen Device
COLOR_TEXT_BG    = (20, 20, 20)    # Dark Charcoal
COLOR_ACCENT     = (0, 210, 255)   # Amber / Orange

try:
    while True:
        success, frame = camera.read()
        if not success:
            time.sleep(0.01)
            continue

        person_filter.update_frame(frame)
        frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # ── Detect BOTH persons AND screen devices ──
        results = model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            classes=DETECT_CLASSES,
            conf=CONFIDENCE,
            imgsz=IMAGE_SIZE,
            device=DEVICE,
            verbose=False
        )

        result = results[0]
        output = frame.copy()

        real_count = 0
        total_count = 0
        filtered_count = 0
        screen_boxes = np.array([])
        active_person_ids = set()

        if result.boxes is not None and len(result.boxes) > 0:
            boxes = result.boxes
            all_classes = boxes.cls.cpu().numpy().astype(int)
            all_coords = boxes.xyxy.cpu().numpy()
            all_confs = boxes.conf.cpu().numpy()

            # ── Screen Devices (Phone, Laptop, TV) ──
            screen_mask = np.isin(all_classes, list(SCREEN_CLASSES))
            screen_boxes = all_coords[screen_mask]
            screen_confs = all_confs[screen_mask]

            for sbox, sconf in zip(screen_boxes, screen_confs):
                sx1, sy1, sx2, sy2 = sbox.astype(int)
                cv2.rectangle(output, (sx1, sy1), (sx2, sy2), COLOR_SCREEN_BOX, 2)
                slabel = f"SCREEN {sconf:.0%}"
                (tw, th), _ = cv2.getTextSize(slabel, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                cv2.rectangle(output, (sx1, sy2 + 2), (sx1 + tw + 6, sy2 + th + 8), COLOR_TEXT_BG, -1)
                cv2.putText(output, slabel, (sx1 + 3, sy2 + th + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_SCREEN_BOX, 1)

            # ── Person Detections ──
            if boxes.id is not None:
                all_ids = boxes.id.cpu().numpy().astype(int)
                person_mask = (all_classes == PERSON_CLASS)

                if np.any(person_mask):
                    person_ids = all_ids[person_mask]
                    person_confs = all_confs[person_mask]
                    person_coords = all_coords[person_mask]

                    # Apply NMS on person boxes to remove duplicate detections on screen
                    nms_indices = cv2.dnn.NMSBoxes(
                        bboxes=[[int(b[0]), int(b[1]), int(b[2]-b[0]), int(b[3]-b[1])] for b in person_coords],
                        scores=person_confs.tolist(),
                        score_threshold=CONFIDENCE,
                        nms_threshold=0.40
                    )

                    if len(nms_indices) > 0:
                        nms_indices = np.array(nms_indices).flatten()
                        person_ids = person_ids[nms_indices]
                        person_confs = person_confs[nms_indices]
                        person_coords = person_coords[nms_indices]

                    total_count = len(person_ids)

                    for i, (track_id, conf, box) in enumerate(
                        zip(person_ids, person_confs, person_coords)
                    ):
                        active_person_ids.add(track_id)
                        x1, y1, x2, y2 = box

                        # Track history
                        center_x = (x1 + x2) / 2
                        center_y = (y1 + y2) / 2
                        if track_id not in track_history:
                            track_history[track_id] = []
                        track_history[track_id].append((center_x, center_y))
                        if len(track_history[track_id]) > MAX_HISTORY:
                            track_history[track_id].pop(0)

                        pts = np.array(track_history[track_id], dtype=np.int32)
                        if len(pts) > 1:
                            cv2.polylines(output, [pts], False, (180, 180, 180), 1)

                        # ── Multi-Signal Evaluation ──
                        score, reason, is_real = person_filter.evaluate_person(
                            frame, frame_gray, box, track_id, float(conf),
                            person_coords, i, screen_boxes
                        )

                        if is_real:
                            real_count += 1
                            color = COLOR_REAL
                            label = f"REAL #{track_id} {conf:.0%} [{score:.2f}]"
                        else:
                            filtered_count += 1
                            color = COLOR_FILTERED
                            tag = reason if reason != "OK" else "SCREEN/PHOTO"
                            label = f"{tag} #{track_id} {conf:.0%} [{score:.2f}]"

                        ix1, iy1 = int(x1), int(y1)
                        ix2, iy2 = int(x2), int(y2)
                        cv2.rectangle(output, (ix1, iy1), (ix2, iy2), color, 2)

                        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
                        cv2.rectangle(output, (ix1, max(0, iy1 - th - 10)), (ix1 + tw + 8, iy1), COLOR_TEXT_BG, -1)
                        cv2.rectangle(output, (ix1, max(0, iy1 - th - 10)), (ix1 + tw + 8, iy1), color, 1)
                        cv2.putText(output, label, (ix1 + 4, iy1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 1)

        person_filter.post_frame_update(frame_gray, active_person_ids)

        # ── FPS Calculation ──
        fps_counter += 1
        elapsed = time.time() - fps_timer
        if elapsed >= 1.0:
            fps = fps_counter / elapsed
            fps_counter = 0
            fps_timer = time.time()

        # ── Futuristic HUD Card Overlay ──
        hud_bg = output.copy()
        cv2.rectangle(hud_bg, (15, 15), (390, 160), (15, 15, 15), -1)
        cv2.addWeighted(hud_bg, 0.65, output, 0.35, 0, output)
        cv2.rectangle(output, (15, 15), (390, 160), (60, 60, 60), 1)

        cv2.putText(output, "AI CROWD INTELLIGENCE", (30, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.65, COLOR_ACCENT, 2)
        cv2.putText(output, f"Real People:   {real_count}", (30, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.65, COLOR_REAL, 2)
        cv2.putText(output, f"Filtered Out:  {filtered_count}  (Total: {total_count})", (30, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_FILTERED, 2)
        cv2.putText(output, f"FPS: {fps:.1f}  |  Screens Detected: {len(screen_boxes)}", (30, 135), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (220, 220, 220), 1)

        cv2.imshow("AI Crowd Intelligence - Real Person Detection", output)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

finally:
    camera.stop()
    cv2.destroyAllWindows()
    print("System stopped.")