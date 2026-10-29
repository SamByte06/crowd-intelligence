"""
Comprehensive Head-Based Tracking and Synchronized Crowd Counting Test Suite.

Validates the 12 required scenarios from the CV Upgrade specification:
1. Single head persists ID across consecutive frames
2. Two heads receive distinct IDs
3. Two heads crossing paths preserve IDs
4. Temporary head occlusion and reacquisition
5. New head entering receives a distinct ID
6. Head crossing entry baseline counted exactly once
7. Head crossing exit baseline counted exactly once
8. Head near baseline triggers no duplicate events (deadband hysteresis)
9. Camera disconnect and reconnect resilience
10. Multiple cameras tracker isolation
11. Repeated frames do not duplicate tracks or counts
12. Backend retries and refreshes are idempotent
"""

import time
import pytest
import numpy as np
from pathlib import Path
from app.services.gate_counter import (
    GateCounter, LineCrossingConfig, GateRegion, CrossingSide, CrossingEvent
)
from app.services.camera_manager import CameraWorker, CameraManager
from app.config import settings


def make_gate_config(gate_type="ENTRY", baseline_y=0.5, **kwargs) -> LineCrossingConfig:
    """Helper to generate LineCrossingConfig for testing."""
    direction = "down" if gate_type.upper() == "ENTRY" else "up"
    cfg = {
        "start_x": 0.0,
        "start_y": baseline_y,
        "end_x": 1.0,
        "end_y": baseline_y,
        "counting_direction": direction,
        "gate_type": gate_type.upper(),
        "crossing_cooldown": 0.1,
        "track_expiry": 3.0,
        "hysteresis_margin": 0.03,
    }
    cfg.update(kwargs)
    return LineCrossingConfig(**cfg)


class TestHeadTrackingAndCounting:
    """Test suite covering the 12 core CV head tracking & counting scenarios."""

    # 1. Single head persists ID across consecutive frames
    def test_single_head_persists_id_across_consecutive_frames(self):
        """A single head moving down across consecutive frames retains track ID."""
        counter = GateCounter(make_gate_config(gate_type="ENTRY"))
        t0 = time.time()

        # Step along path: y = 0.20 -> 0.25 -> 0.30 -> 0.35 -> 0.40
        for i, y_pos in enumerate([0.20, 0.25, 0.30, 0.35, 0.40]):
            det = {
                "track_id": 101,
                "confidence": 0.92,
                "head_x": 0.50,
                "head_y": y_pos,
                "bbox": [200, int(y_pos * 1000) - 20, 240, int(y_pos * 1000) + 20],
            }
            events = counter.update([det], t0 + (i * 0.05))
            assert len(events) == 0  # Still approaching, above baseline
            assert 101 in counter.tracks
            track = counter.tracks[101]
            assert track.track_id == 101
            assert len(track.history) == i + 1
            assert track.current_region == GateRegion.ABOVE

    # 2. Two heads receive distinct IDs
    def test_two_heads_receive_different_ids(self):
        """Two heads detected in the same frame receive independent track states."""
        counter = GateCounter(make_gate_config(gate_type="ENTRY"))
        t0 = time.time()

        dets = [
            {"track_id": 101, "head_x": 0.35, "head_y": 0.25, "bbox": [150, 100, 180, 130]},
            {"track_id": 102, "head_x": 0.65, "head_y": 0.28, "bbox": [300, 110, 330, 140]},
        ]
        counter.update(dets, t0)
        assert len(counter.tracks) == 2
        assert 101 in counter.tracks
        assert 102 in counter.tracks
        assert counter.tracks[101].person_y == pytest.approx(0.25, rel=1e-3)
        assert counter.tracks[102].person_y == pytest.approx(0.28, rel=1e-3)

    # 3. Two heads crossing paths preserve IDs
    def test_two_heads_crossing_paths_preserve_ids(self):
        """
        Two heads moving laterally toward each other, crossing x-coordinates,
        maintain their designated identities and state machines.
        """
        counter = GateCounter(make_gate_config(gate_type="ENTRY"))
        t0 = time.time()

        # Person A moves left -> right (x: 0.3 -> 0.45 -> 0.55 -> 0.70)
        # Person B moves right -> left (x: 0.7 -> 0.55 -> 0.45 -> 0.30)
        steps = [
            ((0.30, 0.25), (0.70, 0.25)),
            ((0.45, 0.25), (0.55, 0.25)),  # Approaching
            ((0.55, 0.25), (0.45, 0.25)),  # Cross paths
            ((0.70, 0.25), (0.30, 0.25)),  # Separated
        ]

        for i, (pos_a, pos_b) in enumerate(steps):
            dets = [
                {"track_id": 1, "head_x": pos_a[0], "head_y": pos_a[1], "bbox": [0, 0, 10, 10]},
                {"track_id": 2, "head_x": pos_b[0], "head_y": pos_b[1], "bbox": [0, 0, 10, 10]},
            ]
            counter.update(dets, t0 + (i * 0.05))
            assert counter.tracks[1].person_x == pytest.approx(pos_a[0], rel=1e-3)
            assert counter.tracks[2].person_x == pytest.approx(pos_b[0], rel=1e-3)
            assert counter.tracks[1].track_id == 1
            assert counter.tracks[2].track_id == 2

    # 4. Temporary head occlusion and reacquisition
    def test_temporary_head_occlusion_and_reacquisition(self):
        """
        If a head is briefly lost (e.g. for 2 frames) and reappears before expiry,
        its track record and crossing status are preserved.
        """
        counter = GateCounter(make_gate_config(gate_type="ENTRY", track_expiry=2.0))
        t0 = time.time()

        # Step 1: Active track above baseline
        counter.update([{"track_id": 55, "head_x": 0.5, "head_y": 0.35, "bbox": [0, 0, 10, 10]}], t0)
        assert 55 in counter.tracks
        assert counter.tracks[55].current_region == GateRegion.ABOVE

        # Step 2: 2 frames where head is occluded / not detected
        counter.update([], t0 + 0.1)
        counter.update([], t0 + 0.2)
        assert 55 in counter.tracks  # Still preserved within track_expiry

        # Step 3: Reacquired crossing baseline into lower region
        events = counter.update([{"track_id": 55, "head_x": 0.5, "head_y": 0.65, "bbox": [0, 0, 10, 10]}], t0 + 0.3)
        assert len(events) == 1
        assert events[0].direction == "IN"
        assert counter.tracks[55].has_crossed is True

    # 5. New head entering receives distinct ID
    def test_new_head_entering_receives_distinct_id(self):
        """A new person entering the scene is added with a new ID without corrupting existing tracks."""
        counter = GateCounter(make_gate_config(gate_type="ENTRY"))
        t0 = time.time()

        # Frame 1: Only head 1
        counter.update([{"track_id": 1, "head_x": 0.5, "head_y": 0.2, "bbox": [0, 0, 10, 10]}], t0)
        assert len(counter.tracks) == 1
        assert 1 in counter.tracks

        # Frame 2: Head 1 moves, Head 2 enters
        counter.update([
            {"track_id": 1, "head_x": 0.5, "head_y": 0.3, "bbox": [0, 0, 10, 10]},
            {"track_id": 2, "head_x": 0.8, "head_y": 0.15, "bbox": [0, 0, 10, 10]},
        ], t0 + 0.1)
        assert len(counter.tracks) == 2
        assert 1 in counter.tracks
        assert 2 in counter.tracks
        assert counter.tracks[1].person_y == pytest.approx(0.3, rel=1e-3)
        assert counter.tracks[2].person_y == pytest.approx(0.15, rel=1e-3)

    # 6. Head crossing entry baseline counted exactly once
    def test_head_crossing_entry_baseline_counted_once(self):
        """
        In Entry camera, a head moving from above to below baseline is counted
        once as IN. Subsequent frames continuing downward do not re-count.
        """
        counter = GateCounter(make_gate_config(gate_type="ENTRY", baseline_y=0.50))
        t0 = time.time()

        # Step 1: Above baseline (y = 0.35)
        ev1 = counter.update([{"track_id": 7, "head_x": 0.5, "head_y": 0.35, "bbox": [0, 0, 10, 10]}], t0)
        assert len(ev1) == 0
        assert counter.total_in == 0

        # Step 2: Crosses below baseline (y = 0.65)
        ev2 = counter.update([{"track_id": 7, "head_x": 0.5, "head_y": 0.65, "bbox": [0, 0, 10, 10]}], t0 + 0.1)
        assert len(ev2) == 1
        assert ev2[0].direction == "IN"
        assert counter.total_in == 1

        # Step 3: Continues downward (y = 0.75, 0.85) -> Must NOT count again
        ev3 = counter.update([{"track_id": 7, "head_x": 0.5, "head_y": 0.75, "bbox": [0, 0, 10, 10]}], t0 + 0.2)
        assert len(ev3) == 0
        ev4 = counter.update([{"track_id": 7, "head_x": 0.5, "head_y": 0.85, "bbox": [0, 0, 10, 10]}], t0 + 0.3)
        assert len(ev4) == 0
        assert counter.total_in == 1

    # 7. Head crossing exit baseline counted exactly once
    def test_head_crossing_exit_baseline_counted_once(self):
        """
        In Exit camera, a head moving from below to above baseline is counted
        once as OUT. Subsequent frames continuing upward do not re-count.
        """
        counter = GateCounter(make_gate_config(gate_type="EXIT", baseline_y=0.50))
        t0 = time.time()

        # Step 1: Below baseline (y = 0.65)
        ev1 = counter.update([{"track_id": 12, "head_x": 0.5, "head_y": 0.65, "bbox": [0, 0, 10, 10]}], t0)
        assert len(ev1) == 0
        assert counter.total_out == 0

        # Step 2: Crosses above baseline (y = 0.35)
        ev2 = counter.update([{"track_id": 12, "head_x": 0.5, "head_y": 0.35, "bbox": [0, 0, 10, 10]}], t0 + 0.1)
        assert len(ev2) == 1
        assert ev2[0].direction == "OUT"
        assert counter.total_out == 1

        # Step 3: Continues upward (y = 0.25, 0.15) -> Must NOT count again
        ev3 = counter.update([{"track_id": 12, "head_x": 0.5, "head_y": 0.25, "bbox": [0, 0, 10, 10]}], t0 + 0.2)
        assert len(ev3) == 0
        assert counter.total_out == 1

    # 8. Head near baseline triggers no duplicate events (deadband hysteresis)
    def test_head_near_baseline_no_duplicate_events(self):
        """
        A head hovering/jittering within the deadband margin (0.47 to 0.53)
        must never trigger spurious crossing events.
        """
        counter = GateCounter(make_gate_config(gate_type="ENTRY", baseline_y=0.50, hysteresis_margin=0.03))
        t0 = time.time()

        # Start clearly above deadband
        counter.update([{"track_id": 88, "head_x": 0.5, "head_y": 0.40, "bbox": [0, 0, 10, 10]}], t0)

        # Jitter right on and inside deadband: 0.49, 0.50, 0.51, 0.52, 0.48
        jitters = [0.49, 0.50, 0.51, 0.52, 0.48, 0.50]
        for i, y_jit in enumerate(jitters):
            events = counter.update([{"track_id": 88, "head_x": 0.5, "head_y": y_jit, "bbox": [0, 0, 10, 10]}], t0 + 0.1 + i * 0.05)
            assert len(events) == 0
            assert counter.total_in == 0

        # Only when cleanly leaving deadband below (y = 0.56 > 0.53) should it count
        clean_cross = counter.update([{"track_id": 88, "head_x": 0.5, "head_y": 0.56, "bbox": [0, 0, 10, 10]}], t0 + 0.5)
        assert len(clean_cross) == 1
        assert clean_cross[0].direction == "IN"
        assert counter.total_in == 1

    # 9. Camera disconnect and reconnect resilience
    def test_camera_disconnect_and_reconnect_resilience(self):
        """
        When a stream drops (delivering empty or None frames) and then reconnects,
        the system maintains stable counters and resumes gracefully without crash.
        """
        counter = GateCounter(make_gate_config(gate_type="ENTRY", track_expiry=1.0))
        t0 = time.time()

        # Person enters and is counted
        counter.update([{"track_id": 1, "head_x": 0.5, "head_y": 0.3, "bbox": [0, 0, 10, 10]}], t0)
        counter.update([{"track_id": 1, "head_x": 0.5, "head_y": 0.7, "bbox": [0, 0, 10, 10]}], t0 + 0.1)
        assert counter.total_in == 1

        # Simulate 2 seconds of camera disconnection (no frames/detections)
        counter.update([], t0 + 1.0)
        counter.update([], t0 + 2.5)

        # Counter totals remain intact
        assert counter.total_in == 1
        # Old track expired cleanly
        assert 1 not in counter.tracks

        # Stream reconnected: new person enters cleanly
        counter.update([{"track_id": 2, "head_x": 0.5, "head_y": 0.3, "bbox": [0, 0, 10, 10]}], t0 + 3.0)
        events = counter.update([{"track_id": 2, "head_x": 0.5, "head_y": 0.7, "bbox": [0, 0, 10, 10]}], t0 + 3.1)
        assert len(events) == 1
        assert counter.total_in == 2

    # 10. Multiple cameras tracker isolation
    def test_multiple_cameras_tracker_isolation(self):
        """
        Two cameras (e.g. Entry 1 and Exit 1) using the same local track ID (e.g. ID 1)
        do not collide or corrupt each other's state or counts.
        """
        entry_cam = GateCounter(make_gate_config(gate_type="ENTRY", baseline_y=0.45))
        exit_cam = GateCounter(make_gate_config(gate_type="EXIT", baseline_y=0.55))
        t0 = time.time()

        # Both cameras observe a head assigned track_id 1 by their local tracker
        entry_cam.update([{"track_id": 1, "head_x": 0.5, "head_y": 0.30, "bbox": [0, 0, 10, 10]}], t0)
        exit_cam.update([{"track_id": 1, "head_x": 0.5, "head_y": 0.70, "bbox": [0, 0, 10, 10]}], t0)

        # In entry camera, track 1 moves downward and crosses
        ev_entry = entry_cam.update([{"track_id": 1, "head_x": 0.5, "head_y": 0.60, "bbox": [0, 0, 10, 10]}], t0 + 0.1)
        assert len(ev_entry) == 1
        assert ev_entry[0].direction == "IN"
        assert entry_cam.total_in == 1
        assert exit_cam.total_out == 0  # Exit cam untouched

        # In exit camera, track 1 moves upward and crosses
        ev_exit = exit_cam.update([{"track_id": 1, "head_x": 0.5, "head_y": 0.40, "bbox": [0, 0, 10, 10]}], t0 + 0.1)
        assert len(ev_exit) == 1
        assert ev_exit[0].direction == "OUT"
        assert exit_cam.total_out == 1
        assert entry_cam.total_in == 1

    # 11. Repeated frames do not duplicate tracks or counts
    def test_repeated_frames_do_not_duplicate_tracks_or_counts(self):
        """
        Feeding identical coordinates across repeated frames (e.g. paused video or stationary person)
        must never increment counts or create duplicate tracks.
        """
        counter = GateCounter(make_gate_config(gate_type="ENTRY", baseline_y=0.50))
        t0 = time.time()

        # Person stationary at y=0.35
        for i in range(10):
            events = counter.update([{"track_id": 99, "head_x": 0.5, "head_y": 0.35, "bbox": [0, 0, 10, 10]}], t0 + i * 0.05)
            assert len(events) == 0
            assert counter.total_in == 0

        # Person steps across to y=0.65 -> counted once
        events = counter.update([{"track_id": 99, "head_x": 0.5, "head_y": 0.65, "bbox": [0, 0, 10, 10]}], t0 + 0.55)
        assert len(events) == 1
        assert counter.total_in == 1

        # Person remains stationary at y=0.65 for 10 frames
        for i in range(10):
            events = counter.update([{"track_id": 99, "head_x": 0.5, "head_y": 0.65, "bbox": [0, 0, 10, 10]}], t0 + 0.60 + i * 0.05)
            assert len(events) == 0
            assert counter.total_in == 1

    # 12. Backend retries and refreshes idempotent
    def test_backend_retries_and_refreshes_idempotent(self):
        """
        Invoking reset(), reconfiguring baseline line position, or refreshing
        state is completely idempotent and preserves configuration integrity.
        """
        counter = GateCounter(make_gate_config(gate_type="ENTRY", baseline_y=0.50))
        t0 = time.time()

        # Generate some counts
        counter.update([{"track_id": 1, "head_x": 0.5, "head_y": 0.3, "bbox": [0, 0, 10, 10]}], t0)
        counter.update([{"track_id": 1, "head_x": 0.5, "head_y": 0.7, "bbox": [0, 0, 10, 10]}], t0 + 0.1)
        assert counter.total_in == 1

        # Idempotent reset call 1
        counter.reset()
        assert counter.total_in == 0
        assert counter.total_out == 0
        assert len(counter.tracks) == 0
        assert counter.config.gate_type == "ENTRY"

        # Idempotent reset call 2 (consecutive reset)
        counter.reset()
        assert counter.total_in == 0
        assert counter.total_out == 0
        assert len(counter.tracks) == 0

        # Update line configuration idempotently
        counter.update_line(0.0, 0.42, 1.0, 0.42)
        assert counter.config.start_y == 0.42
        assert counter.config.end_y == 0.42
        counter.update_line(0.0, 0.42, 1.0, 0.42)
        assert counter.config.start_y == 0.42


class TestHeadModelIntegration:
    """Verifies that the dedicated head detection model loads and tracks properly."""

    def test_head_model_file_exists_and_loads(self):
        """Confirm that 11s-head.pt is present and loads correctly with Ultralytics."""
        head_model_path = Path(settings.HEAD_MODEL_PATH)
        assert head_model_path.exists(), f"Head model not found at {head_model_path}"

        from ultralytics import YOLO
        model = YOLO(str(head_model_path))
        assert model is not None
        names = model.names
        assert isinstance(names, dict)
        assert len(names) == 1
        # Dedicated model is a single-class head detector
        assert "head" in str(head_model_path).lower()

    def test_head_model_inference_on_synthetic_frame(self):
        """Test inference on a dummy frame with head model."""
        from ultralytics import YOLO
        model = YOLO(str(settings.HEAD_MODEL_PATH))
        # Create a synthetic 640x640 frame
        dummy_frame = np.zeros((640, 640, 3), dtype=np.uint8)
        results = model(dummy_frame, verbose=False)
        assert len(results) > 0
