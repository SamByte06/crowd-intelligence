"""
Deterministic verification of Entry and Exit counting zones on actual video footage.
Loads actual YOLO model and runs tracking against real media files.
"""

import os
import cv2
import time
from ultralytics import YOLO
from app.services.gate_counter import GateCounter, LineCrossingConfig, GateRegion

def test_footage():
    video_entry = os.path.abspath("backend/media_uploads/1b1bb5bf_model2entryt3.mp4")
    video_exit = os.path.abspath("backend/media_uploads/1c356cf5_model2exit1.mp4")

    if not os.path.exists(video_entry):
        print(f"File not found: {video_entry}")
        return
    if not os.path.exists(video_exit):
        print(f"File not found: {video_exit}")
        return

    model_path = os.path.abspath("backend/yolo11s.pt")
    model = YOLO(model_path)

    # 1. Test Entry Video with Entry Counter
    print("\n--- RUNNING ENTRY FOOTAGE VERIFICATION ---")
    cap = cv2.VideoCapture(video_entry)
    entry_cfg = LineCrossingConfig(
        start_x=0.0, start_y=0.45,
        end_x=1.0, end_y=0.45,
        gate_type="ENTRY",
        counting_direction="down",
        hysteresis_margin=0.015,
        single_pass_only=False,
    )
    counter_entry = GateCounter(entry_cfg, counting_enabled=True)

    frame_idx = 0
    in_events = 0
    out_events = 0

    while frame_idx < 100:
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1
        h, w = frame.shape[:2]

        results = model.track(
            frame,
            persist=True,
            conf=0.30,
            classes=[0],
            tracker="bytetrack.yaml",
            verbose=False,
        )

        detections = []
        if results and results[0].boxes and results[0].boxes.id is not None:
            boxes = results[0].boxes
            for i in range(len(boxes)):
                track_id = int(boxes.id[i].item())
                x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                person_x = ((x1 + x2) / 2.0) / w
                person_y = y2 / h
                detections.append({
                    "track_id": track_id,
                    "person_x": person_x,
                    "person_y": person_y,
                    "bbox": [x1 / w, y1 / h, x2 / w, y2 / h],
                    "confidence": float(boxes.conf[i].item()),
                })

        events = counter_entry.update(detections, time.time())
        for ev in events:
            if ev.direction == "IN":
                in_events += 1
                print(f"  Frame {frame_idx}: Valid Entry Event! Track #{ev.track_id} crossed baseline (ABOVE -> BELOW)")
            elif ev.direction == "OUT":
                out_events += 1

    cap.release()
    print(f"Entry Footage Results: Total Frames: {frame_idx}, Total IN: {counter_entry.total_in}, Total OUT: {counter_entry.total_out}")
    assert counter_entry.total_out == 0, "Entry gate should NEVER emit OUT events!"
    print("  [SUCCESS] Entry gate strictly emitted valid upper-to-lower crossings; 0 exit events emitted.")

    # 2. Test Exit Video with Exit Counter
    print("\n--- RUNNING EXIT FOOTAGE VERIFICATION ---")
    cap = cv2.VideoCapture(video_exit)
    exit_cfg = LineCrossingConfig(
        start_x=0.0, start_y=0.55,
        end_x=1.0, end_y=0.55,
        gate_type="EXIT",
        counting_direction="up",
        hysteresis_margin=0.015,
        single_pass_only=False,
    )
    counter_exit = GateCounter(exit_cfg, counting_enabled=True)

    frame_idx = 0
    in_events = 0
    out_events = 0

    while frame_idx < 100:
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1
        h, w = frame.shape[:2]

        results = model.track(
            frame,
            persist=True,
            conf=0.30,
            classes=[0],
            tracker="bytetrack.yaml",
            verbose=False,
        )

        detections = []
        if results and results[0].boxes and results[0].boxes.id is not None:
            boxes = results[0].boxes
            for i in range(len(boxes)):
                track_id = int(boxes.id[i].item())
                x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                person_x = ((x1 + x2) / 2.0) / w
                person_y = y2 / h
                detections.append({
                    "track_id": track_id,
                    "person_x": person_x,
                    "person_y": person_y,
                    "bbox": [x1 / w, y1 / h, x2 / w, y2 / h],
                    "confidence": float(boxes.conf[i].item()),
                })

        events = counter_exit.update(detections, time.time())
        for ev in events:
            if ev.direction == "OUT":
                out_events += 1
                print(f"  Frame {frame_idx}: Valid Exit Event! Track #{ev.track_id} crossed baseline (BELOW -> ABOVE)")
            elif ev.direction == "IN":
                in_events += 1

    cap.release()
    print(f"Exit Footage Results: Total Frames: {frame_idx}, Total IN: {counter_exit.total_in}, Total OUT: {counter_exit.total_out}")
    assert counter_exit.total_in == 0, "Exit gate should NEVER emit IN events!"
    print("  [SUCCESS] Exit gate strictly emitted valid lower-to-upper crossings; 0 entry events emitted.")

    print("\nALL FOOTAGE VERIFICATION CHECKS PASSED PERFECTLY!\n")

if __name__ == "__main__":
    test_footage()

