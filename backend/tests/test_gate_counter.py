"""
Tests for the GateCounter — virtual line-crossing detection.

Tests cover: entry/exit crossing, direction classification, duplicate prevention,
hysteresis, track expiry, and multiple gates.
"""

import time
import pytest
from app.services.gate_counter import (
    GateCounter, LineCrossingConfig, CrossingSide, CrossingEvent,
)


def make_config(**kwargs) -> LineCrossingConfig:
    """Create a LineCrossingConfig with defaults."""
    defaults = {
        "start_x": 0.0,
        "start_y": 0.5,
        "end_x": 1.0,
        "end_y": 0.5,
        "counting_direction": "down",
        "crossing_cooldown": 0.1,
        "track_expiry": 5.0,
    }
    defaults.update(kwargs)
    return LineCrossingConfig(**defaults)


class TestLineCrossing:
    """Test basic line-crossing detection."""

    def test_entry_crossing_top_to_bottom(self):
        """A person moving from top to bottom should count as IN (direction=down)."""
        counter = GateCounter(make_config(counting_direction="down"))
        now = time.time()

        # Person above the line (y=0.3 < 0.5)
        events = counter.update([{"track_id": 1, "cx": 0.5, "cy": 0.3}], now)
        assert len(events) == 0

        # Person crosses to below the line (y=0.7 > 0.5)
        events = counter.update([{"track_id": 1, "cx": 0.5, "cy": 0.7}], now + 1)
        assert len(events) == 1
        assert events[0].direction == "IN"
        assert events[0].track_id == 1

    def test_exit_crossing_bottom_to_top(self):
        """A person moving from bottom to top should count as OUT (direction=down)."""
        counter = GateCounter(make_config(counting_direction="down"))
        now = time.time()

        # Person below the line
        events = counter.update([{"track_id": 2, "cx": 0.5, "cy": 0.7}], now)
        assert len(events) == 0

        # Person crosses to above the line
        events = counter.update([{"track_id": 2, "cx": 0.5, "cy": 0.3}], now + 1)
        assert len(events) == 1
        assert events[0].direction == "OUT"

    def test_entry_crossing_direction_up(self):
        """direction=up: bottom-to-top is IN."""
        counter = GateCounter(make_config(counting_direction="up"))
        now = time.time()

        counter.update([{"track_id": 1, "cx": 0.5, "cy": 0.7}], now)
        events = counter.update([{"track_id": 1, "cx": 0.5, "cy": 0.3}], now + 1)
        assert len(events) == 1
        assert events[0].direction == "IN"

    def test_no_crossing_same_side(self):
        """Movement on the same side of line should not generate events."""
        counter = GateCounter(make_config())
        now = time.time()

        counter.update([{"track_id": 1, "cx": 0.5, "cy": 0.3}], now)
        events = counter.update([{"track_id": 1, "cx": 0.6, "cy": 0.2}], now + 1)
        assert len(events) == 0

    def test_vertical_line_crossing(self):
        """Test crossing a vertical line (left-right)."""
        config = make_config(
            start_x=0.5, start_y=0.0,
            end_x=0.5, end_y=1.0,
            counting_direction="right",
        )
        counter = GateCounter(config)
        now = time.time()

        # Person on left (x=0.3 < 0.5)
        counter.update([{"track_id": 1, "cx": 0.3, "cy": 0.5}], now)

        # Person crosses to right (x=0.7 > 0.5)
        events = counter.update([{"track_id": 1, "cx": 0.7, "cy": 0.5}], now + 1)
        assert len(events) == 1
        assert events[0].direction == "IN"


class TestDuplicatePrevention:
    """Test that duplicate crossings are prevented."""

    def test_cooldown_prevents_immediate_recount(self):
        """Same track crossing back and forth quickly should be blocked by cooldown."""
        counter = GateCounter(make_config(crossing_cooldown=2.0))
        now = time.time()

        # Cross in
        counter.update([{"track_id": 1, "cx": 0.5, "cy": 0.3}], now)
        events = counter.update([{"track_id": 1, "cx": 0.5, "cy": 0.7}], now + 0.5)
        assert len(events) == 1

        # Try to cross back within cooldown
        events = counter.update([{"track_id": 1, "cx": 0.5, "cy": 0.3}], now + 1.0)
        assert len(events) == 0  # Blocked by cooldown

        # Cross back after cooldown
        events = counter.update([{"track_id": 1, "cx": 0.5, "cy": 0.7}], now + 3.0)
        assert len(events) == 1  # Allowed

    def test_different_tracks_counted_independently(self):
        """Two different tracks should be counted independently."""
        counter = GateCounter(make_config())
        now = time.time()

        # Track 1 above line
        counter.update([
            {"track_id": 1, "cx": 0.3, "cy": 0.3},
            {"track_id": 2, "cx": 0.7, "cy": 0.3},
        ], now)

        # Both cross
        events = counter.update([
            {"track_id": 1, "cx": 0.3, "cy": 0.7},
            {"track_id": 2, "cx": 0.7, "cy": 0.7},
        ], now + 1)
        assert len(events) == 2
        assert counter.total_in == 2

    def test_jitter_on_line_no_duplicate(self):
        """Points very close to the line should not trigger crossings."""
        counter = GateCounter(make_config())
        now = time.time()

        # Start clearly above
        counter.update([{"track_id": 1, "cx": 0.5, "cy": 0.3}], now)

        # Hover near line
        events = counter.update([{"track_id": 1, "cx": 0.5, "cy": 0.499}], now + 0.1)
        assert len(events) == 0

        events = counter.update([{"track_id": 1, "cx": 0.5, "cy": 0.501}], now + 0.2)
        assert len(events) == 0  # Still too close to line


class TestTrackExpiry:
    """Test track state cleanup."""

    def test_expired_tracks_removed(self):
        """Tracks not seen for track_expiry seconds should be removed."""
        counter = GateCounter(make_config(track_expiry=2.0))
        now = time.time()

        counter.update([{"track_id": 1, "cx": 0.5, "cy": 0.3}], now)
        assert 1 in counter.tracks

        # Don't include track 1 in next updates
        counter.update([], now + 3.0)
        assert 1 not in counter.tracks


class TestCounts:
    """Test count aggregation."""

    def test_total_counts(self):
        """Verify total_in and total_out accumulate correctly."""
        counter = GateCounter(make_config(crossing_cooldown=0.0))
        now = time.time()

        # 3 entries
        for i in range(3):
            t = now + i * 2
            counter.update([{"track_id": 10 + i, "cx": 0.5, "cy": 0.3}], t)
            counter.update([{"track_id": 10 + i, "cx": 0.5, "cy": 0.7}], t + 0.5)

        # 1 exit
        counter.update([{"track_id": 20, "cx": 0.5, "cy": 0.7}], now + 10)
        counter.update([{"track_id": 20, "cx": 0.5, "cy": 0.3}], now + 10.5)

        counts = counter.get_counts()
        assert counts["total_in"] == 3
        assert counts["total_out"] == 1

    def test_reset(self):
        """Reset should clear all state."""
        counter = GateCounter(make_config())
        now = time.time()

        counter.update([{"track_id": 1, "cx": 0.5, "cy": 0.3}], now)
        counter.update([{"track_id": 1, "cx": 0.5, "cy": 0.7}], now + 1)

        counter.reset()
        assert counter.total_in == 0
        assert counter.total_out == 0
        assert len(counter.tracks) == 0


class TestMultipleGates:
    """Test that multiple gate counters work independently."""

    def test_independent_counters(self):
        """Two gate counters should track independently."""
        entry_counter = GateCounter(make_config(counting_direction="down"))
        exit_counter = GateCounter(make_config(counting_direction="up"))
        now = time.time()

        # Entry gate: person enters (top to bottom)
        entry_counter.update([{"track_id": 1, "cx": 0.5, "cy": 0.3}], now)
        entry_events = entry_counter.update([{"track_id": 1, "cx": 0.5, "cy": 0.7}], now + 1)

        # Exit gate: person exits (bottom to top)
        exit_counter.update([{"track_id": 1, "cx": 0.5, "cy": 0.7}], now)
        exit_events = exit_counter.update([{"track_id": 1, "cx": 0.5, "cy": 0.3}], now + 1)

        assert len(entry_events) == 1
        assert entry_events[0].direction == "IN"
        assert entry_counter.total_in == 1

        assert len(exit_events) == 1
        assert exit_events[0].direction == "IN"  # "IN" because direction=up, bottom-to-top is IN
        assert exit_counter.total_in == 1


class TestDeterministicCountingZones:
    """
    Deterministic verification tests for Entry and Exit gate counting zones,
    directional policies, hysteresis deadbands, and bottom-center reference points.
    """

    # --- ENTRY CAMERA TESTS ---

    def test_entry_above_to_below_counts_exactly_once(self):
        """Entry test 1: A person moves from above the baseline to below it: exactly one entry event."""
        counter = GateCounter(make_config(gate_type="ENTRY", counting_direction="down"))
        now = time.time()

        # Step 1: Initial position above the baseline (y = 0.3 < 0.5)
        ev1 = counter.update([{"track_id": 10, "cx": 0.5, "cy": 0.3}], now)
        assert len(ev1) == 0
        assert counter.total_in == 0

        # Step 2: Crosses below the baseline (y = 0.7 > 0.5)
        ev2 = counter.update([{"track_id": 10, "cx": 0.5, "cy": 0.7}], now + 0.1)
        assert len(ev2) == 1
        assert ev2[0].direction == "IN"
        assert ev2[0].track_id == 10
        assert counter.total_in == 1

    def test_entry_person_remains_below_no_repeated_events(self):
        """Entry test 2: A person detected in entry zone below baseline is counted once, with no repeated events."""
        counter = GateCounter(make_config(gate_type="ENTRY", counting_direction="down"))
        now = time.time()

        # First detected below the baseline (y = 0.7 > 0.5): counted as entry
        ev1 = counter.update([{"track_id": 11, "cx": 0.5, "cy": 0.7}], now)
        assert len(ev1) == 1
        assert ev1[0].direction == "IN"
        assert counter.total_in == 1

        # Continues walking / dwelling below the baseline: no duplicate events emitted
        ev2 = counter.update([{"track_id": 11, "cx": 0.52, "cy": 0.75}], now + 0.1)
        ev3 = counter.update([{"track_id": 11, "cx": 0.48, "cy": 0.80}], now + 0.2)
        ev4 = counter.update([{"track_id": 11, "cx": 0.50, "cy": 0.72}], now + 0.3)

        assert len(ev2) == 0
        assert len(ev3) == 0
        assert len(ev4) == 0
        assert counter.total_in == 1

    def test_entry_approach_and_turn_back_no_event(self):
        """Entry test 3: A person approaches the baseline but turns back: no entry event."""
        counter = GateCounter(make_config(gate_type="ENTRY", counting_direction="down", hysteresis_margin=0.02))
        now = time.time()

        # Approaching baseline from above (line is at 0.5)
        counter.update([{"track_id": 12, "cx": 0.5, "cy": 0.2}], now)
        counter.update([{"track_id": 12, "cx": 0.5, "cy": 0.35}], now + 0.1)
        counter.update([{"track_id": 12, "cx": 0.5, "cy": 0.46}], now + 0.2)  # In upper approach zone

        # Turns back
        ev1 = counter.update([{"track_id": 12, "cx": 0.5, "cy": 0.35}], now + 0.3)
        ev2 = counter.update([{"track_id": 12, "cx": 0.5, "cy": 0.20}], now + 0.4)

        assert len(ev1) == 0
        assert len(ev2) == 0
        assert counter.total_in == 0

    def test_entry_below_to_above_no_event_under_one_way_policy(self):
        """Entry test 4: A person moves from below to above: no exit event under configured one-way entry policy."""
        counter = GateCounter(make_config(gate_type="ENTRY", counting_direction="down"))
        now = time.time()

        # Starts below baseline: counted once as entry
        counter.update([{"track_id": 13, "cx": 0.5, "cy": 0.7}], now)
        assert counter.total_in == 1
        assert counter.total_out == 0

        # Moves above baseline: no exit event emitted
        events = counter.update([{"track_id": 13, "cx": 0.5, "cy": 0.3}], now + 0.1)
        assert len(events) == 0
        assert counter.total_in == 1
        assert counter.total_out == 0

    def test_entry_jitter_around_baseline_no_duplicate(self):
        """Entry test 5: A person jitters around the baseline: no duplicate events."""
        counter = GateCounter(make_config(gate_type="ENTRY", counting_direction="down", hysteresis_margin=0.015))
        now = time.time()

        # 1. Start above
        counter.update([{"track_id": 14, "cx": 0.5, "cy": 0.3}], now)

        # 2. Legitimate crossing into lower region
        ev = counter.update([{"track_id": 14, "cx": 0.5, "cy": 0.65}], now + 0.1)
        assert len(ev) == 1
        assert counter.total_in == 1

        # 3. Jitter in and around deadband (0.50 +/- 0.015 is [0.485, 0.515])
        ev_j1 = counter.update([{"track_id": 14, "cx": 0.5, "cy": 0.505}], now + 0.2)
        ev_j2 = counter.update([{"track_id": 14, "cx": 0.5, "cy": 0.495}], now + 0.3)
        ev_j3 = counter.update([{"track_id": 14, "cx": 0.5, "cy": 0.502}], now + 0.4)
        ev_j4 = counter.update([{"track_id": 14, "cx": 0.5, "cy": 0.65}], now + 0.5)

        assert len(ev_j1) == 0
        assert len(ev_j2) == 0
        assert len(ev_j3) == 0
        assert len(ev_j4) == 0
        assert counter.total_in == 1  # Still exactly one count

    # --- EXIT CAMERA TESTS ---

    def test_exit_below_to_above_counts_exactly_once(self):
        """Exit test 1: A person moves from below the baseline to above it: exactly one exit event."""
        counter = GateCounter(make_config(gate_type="EXIT", counting_direction="up"))
        now = time.time()

        # Step 1: Initial position below baseline (y = 0.7 > 0.5)
        ev1 = counter.update([{"track_id": 20, "cx": 0.5, "cy": 0.7}], now)
        assert len(ev1) == 0
        assert counter.total_out == 0

        # Step 2: Crosses above baseline (y = 0.3 < 0.5)
        ev2 = counter.update([{"track_id": 20, "cx": 0.5, "cy": 0.3}], now + 0.1)
        assert len(ev2) == 1
        assert ev2[0].direction == "OUT"
        assert ev2[0].track_id == 20
        assert counter.total_out == 1

    def test_exit_person_remains_above_no_repeated_events(self):
        """Exit test 2: A person remains above the baseline: no repeated exit events."""
        counter = GateCounter(make_config(gate_type="EXIT", counting_direction="up"))
        now = time.time()

        # First detected above the baseline (y = 0.3 < 0.5)
        ev1 = counter.update([{"track_id": 21, "cx": 0.5, "cy": 0.3}], now)
        assert len(ev1) == 0

        # Continues walking / dwelling above baseline
        ev2 = counter.update([{"track_id": 21, "cx": 0.52, "cy": 0.25}], now + 0.1)
        ev3 = counter.update([{"track_id": 21, "cx": 0.48, "cy": 0.20}], now + 0.2)
        ev4 = counter.update([{"track_id": 21, "cx": 0.50, "cy": 0.28}], now + 0.3)

        assert len(ev2) == 0
        assert len(ev3) == 0
        assert len(ev4) == 0
        assert counter.total_out == 0

    def test_exit_approach_and_turn_back_no_event(self):
        """Exit test 3: A person approaches the baseline but turns back: no exit event."""
        counter = GateCounter(make_config(gate_type="EXIT", counting_direction="up", hysteresis_margin=0.02))
        now = time.time()

        # Approaching baseline from below (line is at 0.5)
        counter.update([{"track_id": 22, "cx": 0.5, "cy": 0.8}], now)
        counter.update([{"track_id": 22, "cx": 0.5, "cy": 0.65}], now + 0.1)
        counter.update([{"track_id": 22, "cx": 0.5, "cy": 0.54}], now + 0.2)

        # Turns back
        ev1 = counter.update([{"track_id": 22, "cx": 0.5, "cy": 0.65}], now + 0.3)
        ev2 = counter.update([{"track_id": 22, "cx": 0.5, "cy": 0.80}], now + 0.4)

        assert len(ev1) == 0
        assert len(ev2) == 0
        assert counter.total_out == 0

    def test_exit_above_to_below_no_event_under_one_way_policy(self):
        """Exit test 4: A person moves from above to below: no exit event under configured one-way policy."""
        counter = GateCounter(make_config(gate_type="EXIT", counting_direction="up"))
        now = time.time()

        counter.update([{"track_id": 23, "cx": 0.5, "cy": 0.3}], now)
        events = counter.update([{"track_id": 23, "cx": 0.5, "cy": 0.7}], now + 0.1)

        assert len(events) == 0
        assert counter.total_out == 0
        assert counter.total_in == 0

    def test_exit_jitter_around_baseline_no_duplicate(self):
        """Exit test 5: A person jitters around the baseline: no duplicate events."""
        counter = GateCounter(make_config(gate_type="EXIT", counting_direction="up", hysteresis_margin=0.015))
        now = time.time()

        # 1. Start below
        counter.update([{"track_id": 24, "cx": 0.5, "cy": 0.7}], now)

        # 2. Legitimate crossing into upper region
        ev = counter.update([{"track_id": 24, "cx": 0.5, "cy": 0.35}], now + 0.1)
        assert len(ev) == 1
        assert counter.total_out == 1

        # 3. Jitter in and around deadband
        ev_j1 = counter.update([{"track_id": 24, "cx": 0.5, "cy": 0.495}], now + 0.2)
        ev_j2 = counter.update([{"track_id": 24, "cx": 0.5, "cy": 0.505}], now + 0.3)
        ev_j3 = counter.update([{"track_id": 24, "cx": 0.5, "cy": 0.498}], now + 0.4)
        ev_j4 = counter.update([{"track_id": 24, "cx": 0.5, "cy": 0.35}], now + 0.5)

        assert len(ev_j1) == 0
        assert len(ev_j2) == 0
        assert len(ev_j3) == 0
        assert len(ev_j4) == 0
        assert counter.total_out == 1  # Still exactly one count

    # --- MULTI-PERSON SIMULTANEOUS CROSSING ---

    def test_simultaneous_multi_person_crossing(self):
        """Verify multiple people crossing simultaneously are counted individually."""
        counter = GateCounter(make_config(gate_type="ENTRY", counting_direction="down"))
        now = time.time()

        # 3 distinct people in upper approach zone
        counter.update([
            {"track_id": 101, "cx": 0.2, "cy": 0.3},
            {"track_id": 102, "cx": 0.5, "cy": 0.35},
            {"track_id": 103, "cx": 0.8, "cy": 0.32},
        ], now)
        assert counter.total_in == 0

        # All 3 cross baseline into lower region in the same frame
        events = counter.update([
            {"track_id": 101, "cx": 0.2, "cy": 0.65},
            {"track_id": 102, "cx": 0.5, "cy": 0.70},
            {"track_id": 103, "cx": 0.8, "cy": 0.68},
        ], now + 0.1)

        assert len(events) == 3
        counted_ids = {e.track_id for e in events}
        assert counted_ids == {101, 102, 103}
        for e in events:
            assert e.direction == "IN"
        assert counter.total_in == 3

    # --- CONSISTENT BOTTOM-CENTER REFERENCE POINT ---

    def test_bottom_center_bounding_box_reference(self):
        """Verify that bottom-center (personX = (x1+x2)/2, personY = y2) is strictly used."""
        counter = GateCounter(make_config(gate_type="ENTRY", counting_direction="down", start_y=0.5, end_y=0.5))
        now = time.time()

        # Bounding box: x1=0.4, y1=0.1, x2=0.6, y2=0.45. Bottom center y2 = 0.45 < 0.5 (ABOVE)
        counter.update([{"track_id": 30, "bbox": [0.4, 0.1, 0.6, 0.45]}], now)
        assert counter.tracks[30].current_region.value == "ABOVE"

        # Bounding box advances: x1=0.4, y1=0.25, x2=0.6, y2=0.60. Bottom center y2 = 0.60 > 0.5 (BELOW)
        events = counter.update([{"track_id": 30, "bbox": [0.4, 0.25, 0.6, 0.60]}], now + 0.1)
        assert len(events) == 1
        assert events[0].direction == "IN"
        assert counter.total_in == 1
