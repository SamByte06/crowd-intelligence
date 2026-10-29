"""
Gate Counter Service — Direction-aware virtual line-crossing detection.

Enforces clear coordinate systems and directional counting zones:
- Video-frame coordinates: origin (0, 0) is top-left, X increases right, Y increases downward.
- Baseline is configured at normalized y = lineY.
- Upper region: personY < lineY - margin (ABOVE the line).
- Lower region: personY > lineY + margin (BELOW the line).
- Deadband hysteresis zone: abs(personY - lineY) <= margin (ON_LINE).
- Consistent person reference point: bottom-center of bounding box ((x1 + x2)/2, y2).
- Entry Gate target side: LOWER region (BELOW). Counted only on valid ABOVE -> BELOW crossings.
- Exit Gate target side: UPPER region (ABOVE). Counted only on valid BELOW -> ABOVE crossings.
- Merely occupying a region never generates counting events.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class GateRegion(Enum):
    """
    Regions relative to the horizontal counting baseline.
    Video coordinates: (0, 0) top-left, Y increases downward.
    """
    ABOVE = "ABOVE"      # Upper region: personY < lineY - margin
    BELOW = "BELOW"      # Lower region: personY > lineY + margin
    ON_LINE = "ON_LINE"  # Hysteresis deadband: abs(personY - lineY) <= margin


class CrossingSide(Enum):
    """Legacy side enum for backward compatibility."""
    POSITIVE = 1  # Lower / BELOW side (y > lineY)
    NEGATIVE = -1 # Upper / ABOVE side (y < lineY)
    ON_LINE = 0   # On the line deadband


@dataclass
class TrackState:
    """Per-track state machine maintaining reference point history and crossing status."""
    track_id: int

    # Primary reference point: Bottom-center of bounding box (personX, personY)
    person_x: float = 0.0
    person_y: float = 0.0
    prev_x: float = 0.0
    prev_y: float = 0.0

    # Region state tracking
    current_region: GateRegion = GateRegion.ON_LINE
    last_stable_region: GateRegion = GateRegion.ON_LINE  # Last confirmed region outside deadband (ABOVE or BELOW)
    initial_region: GateRegion = GateRegion.ON_LINE      # Region where track first appeared

    # Trajectory history: list of (timestamp, person_x, person_y, region)
    history: list[tuple[float, float, float, GateRegion]] = field(default_factory=list)

    # Crossing event lifecycle
    has_crossed: bool = False
    last_crossing_dir: Optional[str] = None              # "IN" or "OUT"
    last_crossing_time: float = 0.0
    cooldown_until: float = 0.0
    cross_count: int = 0

    # Status & audit label
    status_label: str = "TRACKING"                      # "ABOVE", "BELOW", "ON_LINE", "ENTRY EVENT", "EXIT EVENT", "BLOCKED"
    last_seen: float = 0.0
    is_blocked: bool = False
    block_reason: str = ""

    # --- Backward compatibility accessors ---
    @property
    def last_centroid(self) -> tuple[float, float]:
        return (self.person_x, self.person_y)

    @last_centroid.setter
    def last_centroid(self, val: tuple[float, float]):
        self.person_x, self.person_y = val

    @property
    def last_feet(self) -> tuple[float, float]:
        return (self.person_x, self.person_y)

    @last_feet.setter
    def last_feet(self, val: tuple[float, float]):
        self.person_x, self.person_y = val

    @property
    def crossed(self) -> bool:
        return self.has_crossed

    @crossed.setter
    def crossed(self, val: bool):
        self.has_crossed = val

    @property
    def last_side(self) -> CrossingSide:
        if self.current_region == GateRegion.BELOW:
            return CrossingSide.POSITIVE
        elif self.current_region == GateRegion.ABOVE:
            return CrossingSide.NEGATIVE
        return CrossingSide.ON_LINE

    @last_side.setter
    def last_side(self, val):
        pass

    @property
    def last_clear_side(self) -> CrossingSide:
        if self.last_stable_region == GateRegion.BELOW:
            return CrossingSide.POSITIVE
        elif self.last_stable_region == GateRegion.ABOVE:
            return CrossingSide.NEGATIVE
        return CrossingSide.ON_LINE

    @last_clear_side.setter
    def last_clear_side(self, val):
        pass


@dataclass
class LineCrossingConfig:
    """Configuration for a virtual counting baseline."""
    # Normalized coordinates (0.0 to 1.0)
    start_x: float = 0.0
    start_y: float = 0.5
    end_x: float = 1.0
    end_y: float = 0.5
    # Counting direction: "down", "up", "any", "both"
    counting_direction: str = "any"
    gate_type: str = "BIDIRECTIONAL"  # "ENTRY", "EXIT", or "BIDIRECTIONAL"
    single_pass_only: bool = False    # Set True for badge/turnstile passback enforcement
    hysteresis_margin: float = 0.015  # Deadband margin around baseline (1.5% of frame height)
    crossing_cooldown: float = 1.5    # Minimum seconds between crossings for the same track
    track_expiry: float = 30.0        # Expire track after seconds without updates


@dataclass
class CrossingEvent:
    """A confirmed line-crossing event."""
    track_id: int
    direction: str  # "IN" or "OUT"
    timestamp: float
    centroid: tuple[float, float]
    confidence: float = 0.0
    is_blocked: bool = False
    block_reason: str = ""


class GateCounter:
    """
    Directional counting engine with per-track state machines,
    hysteresis deadband protection, and isolated camera configurations.
    """

    def __init__(self, config: LineCrossingConfig, counting_enabled: bool = True):
        self.config = config
        self.counting_enabled = counting_enabled
        self.tracks: dict[int, TrackState] = {}
        self.total_in: int = 0
        self.total_out: int = 0
        self.registered_entered: set[int] = set()
        self.registered_exited: set[int] = set()
        self.blocked_violations: list[dict] = []
        self.last_flash_time: float = 0.0
        self._pending_events: list[CrossingEvent] = []

        # Precompute normal vector for perpendicular distance calculation
        self._update_line_vector()

    def _update_line_vector(self):
        """Compute line coefficients for perpendicular distance determination."""
        dx = self.config.end_x - self.config.start_x
        dy = self.config.end_y - self.config.start_y
        self._normal_x = -dy
        self._normal_y = dx
        length = (self._normal_x ** 2 + self._normal_y ** 2) ** 0.5
        if length > 0:
            self._normal_x /= length
            self._normal_y /= length
        else:
            self._normal_x = 0.0
            self._normal_y = 1.0

    def _get_region(self, x: float, y: float) -> GateRegion:
        """
        Determine which region (ABOVE, BELOW, or ON_LINE deadband) a point is in.

        Video coordinates:
        - (0, 0) is top-left, Y increases downward.
        - Upper region: personY < lineY - margin (ABOVE).
        - Lower region: personY > lineY + margin (BELOW).
        - Hysteresis deadband: abs(personY - lineY) <= margin (ON_LINE).
        """
        # Calculate signed perpendicular distance from (x, y) to baseline
        vx = x - self.config.start_x
        vy = y - self.config.start_y
        dot = vx * self._normal_x + vy * self._normal_y
        margin = getattr(self.config, "hysteresis_margin", 0.015)

        if abs(dot) <= margin:
            return GateRegion.ON_LINE
        return GateRegion.BELOW if dot > 0 else GateRegion.ABOVE

    def _get_side(self, x: float, y: float) -> CrossingSide:
        """Compatibility helper returning CrossingSide."""
        region = self._get_region(x, y)
        if region == GateRegion.BELOW:
            return CrossingSide.POSITIVE
        elif region == GateRegion.ABOVE:
            return CrossingSide.NEGATIVE
        return CrossingSide.ON_LINE

    def update(self, detections: list[dict], current_time: float | None = None) -> list[CrossingEvent]:
        """
        Process a frame's detections and return confirmed line-crossing events.

        Consistently uses bottom-center of bounding box for every tracked person:
        personX = (x1 + x2) / 2
        personY = y2
        """
        now = current_time or time.time()
        events: list[CrossingEvent] = []
        seen_tracks = set()

        is_entry_gate = (str(self.config.gate_type).upper().endswith("ENTRY") or self.config.gate_type == "ENTRY")
        is_exit_gate = (str(self.config.gate_type).upper().endswith("EXIT") or self.config.gate_type == "EXIT")
        cfg_direction = str(self.config.counting_direction).lower()

        for det in detections:
            track_id = det["track_id"]
            seen_tracks.add(track_id)

            # Consistently extract head center reference point (with fallback to person_x/person_y/cx/cy)
            if "head_x" in det and "head_y" in det:
                person_x = det["head_x"]
                person_y = det["head_y"]
            elif "bbox" in det and len(det["bbox"]) >= 4:
                bx1, by1, bx2, by2 = det["bbox"]
                person_x = det.get("person_x", (bx1 + bx2) / 2.0)
                person_y = det.get("person_y", by2)
            else:
                person_x = det.get("person_x", det.get("cx", 0.0))
                person_y = det.get("person_y", det.get("cy", 0.0))

            confidence = det.get("confidence", 0.0)
            current_region = self._get_region(person_x, person_y)

            # 1. New Track Initialization
            if track_id not in self.tracks:
                initial_stable = current_region if current_region != GateRegion.ON_LINE else GateRegion.ON_LINE
                self.tracks[track_id] = TrackState(
                    track_id=track_id,
                    person_x=person_x,
                    person_y=person_y,
                    prev_x=person_x,
                    prev_y=person_y,
                    current_region=current_region,
                    last_stable_region=initial_stable,
                    initial_region=current_region,
                    history=[(now, person_x, person_y, current_region)],
                    has_crossed=False,
                    last_seen=now,
                    status_label="CALIBRATING" if not self.counting_enabled else current_region.value,
                )
                det["region"] = current_region.value
                det["status"] = self.tracks[track_id].status_label
                det["is_blocked"] = False
                det["person_x"] = person_x
                det["person_y"] = person_y

                # ENTRY SECTION: Calculate/count people in the target zone BELOW the baseline
                if self.counting_enabled and is_entry_gate and current_region == GateRegion.BELOW:
                    if self.config.single_pass_only and track_id in self.registered_entered:
                        self.tracks[track_id].is_blocked = True
                        self.tracks[track_id].block_reason = "ALREADY ENTERED (PASSBACK DENIED)"
                        self.tracks[track_id].status_label = "BLOCKED"
                        det["status"] = "BLOCKED"
                        det["is_blocked"] = True
                    else:
                        self.registered_entered.add(track_id)
                        self.total_in += 1
                        self.last_flash_time = now
                        self.tracks[track_id].has_crossed = True
                        self.tracks[track_id].cross_count += 1
                        self.tracks[track_id].last_crossing_dir = "IN"
                        self.tracks[track_id].last_crossing_time = now
                        self.tracks[track_id].cooldown_until = now + self.config.crossing_cooldown
                        self.tracks[track_id].status_label = "ENTRY EVENT"
                        det["status"] = "ENTRY EVENT"

                        ev = CrossingEvent(
                            track_id=track_id,
                            direction="IN",
                            timestamp=now,
                            centroid=(person_x, person_y),
                            confidence=confidence,
                        )
                        events.append(ev)
                        self._pending_events.append(ev)
                        logger.info(f"Entry counted (below baseline): Track #{track_id} | Total IN: {self.total_in}")
                continue

            state = self.tracks[track_id]
            state.prev_x = state.person_x
            state.prev_y = state.person_y
            state.person_x = person_x
            state.person_y = person_y
            state.current_region = current_region
            state.last_seen = now
            state.history.append((now, person_x, person_y, current_region))
            if len(state.history) > 30:
                state.history.pop(0)

            # In calibration mode, track positions but suppress all counting
            if not self.counting_enabled:
                if current_region != GateRegion.ON_LINE:
                    state.last_stable_region = current_region
                state.status_label = "CALIBRATING"
                det["region"] = current_region.value
                det["status"] = "CALIBRATING"
                det["is_blocked"] = False
                det["person_x"] = person_x
                det["person_y"] = person_y
                continue

            # Flagged as blocked by anti-passback
            if state.is_blocked:
                det["region"] = current_region.value
                det["status"] = "BLOCKED"
                det["is_blocked"] = True
                det["block_reason"] = state.block_reason
                det["person_x"] = person_x
                det["person_y"] = person_y
                continue

            # 2. Deadband Handling: hovering inside hysteresis zone does not flip region
            if current_region == GateRegion.ON_LINE:
                det["region"] = current_region.value
                det["status"] = state.status_label
                det["is_blocked"] = False
                det["person_x"] = person_x
                det["person_y"] = person_y
                continue

            # 3. First time entering a stable region from initial deadband
            if state.last_stable_region == GateRegion.ON_LINE:
                state.last_stable_region = current_region
                state.status_label = current_region.value
                det["region"] = current_region.value
                det["status"] = current_region.value
                det["is_blocked"] = False
                det["person_x"] = person_x
                det["person_y"] = person_y
                continue

            # 4. Legitimate Return Handling:
            # If an entered person legitimately returns to the opposite side beyond deadband and cooldown,
            # reset has_crossed so a future crossing can be counted.
            if state.has_crossed and (now >= state.cooldown_until):
                if is_entry_gate and current_region == GateRegion.ABOVE:
                    state.has_crossed = False
                    state.status_label = "ABOVE"
                elif is_exit_gate and current_region == GateRegion.BELOW:
                    state.has_crossed = False
                    state.status_label = "BELOW"
                elif self.config.gate_type == "BIDIRECTIONAL":
                    if current_region != state.last_stable_region:
                        state.has_crossed = False

            # 5. Target Zone Entry & Crossing Detection between Stable Regions
            if is_entry_gate and current_region == GateRegion.BELOW and (not state.has_crossed) and (now >= state.cooldown_until):
                state.last_stable_region = GateRegion.BELOW
                if self.config.single_pass_only and track_id in self.registered_entered:
                    state.is_blocked = True
                    state.block_reason = "ALREADY ENTERED (PASSBACK DENIED)"
                    state.status_label = "BLOCKED"
                    block_ev = CrossingEvent(
                        track_id=track_id,
                        direction="IN",
                        timestamp=now,
                        centroid=(person_x, person_y),
                        confidence=confidence,
                        is_blocked=True,
                        block_reason=state.block_reason,
                    )
                    events.append(block_ev)
                    self._pending_events.append(block_ev)
                    self.blocked_violations.append({
                        "track_id": track_id,
                        "type": "RE_ENTRY_DENIED",
                        "timestamp": now,
                    })
                    logger.warning(f"Anti-Passback: Track #{track_id} re-entry blocked")
                else:
                    self.registered_entered.add(track_id)
                    self.total_in += 1
                    self.last_flash_time = now
                    state.has_crossed = True
                    state.cross_count += 1
                    state.last_crossing_dir = "IN"
                    state.last_crossing_time = now
                    state.cooldown_until = now + self.config.crossing_cooldown
                    state.status_label = "ENTRY EVENT"

                    ev = CrossingEvent(
                        track_id=track_id,
                        direction="IN",
                        timestamp=now,
                        centroid=(person_x, person_y),
                        confidence=confidence,
                    )
                    events.append(ev)
                    self._pending_events.append(ev)
                    logger.info(f"Entry counted: Track #{track_id} (BELOW baseline) | Total IN: {self.total_in}")

            elif current_region != state.last_stable_region:
                crossing_event_type: Optional[str] = None

                # Rule priority:
                # A. Entry Gate:
                # By default, Upper (ABOVE) -> Lower (BELOW) is an Entry ("IN").
                # If operator specifically configured counting_direction="up", then BELOW -> ABOVE is "IN".
                if is_entry_gate:
                    if cfg_direction == "up":
                        if state.last_stable_region == GateRegion.BELOW and current_region == GateRegion.ABOVE:
                            crossing_event_type = "IN"
                    else:
                        if state.last_stable_region == GateRegion.ABOVE and current_region == GateRegion.BELOW:
                            crossing_event_type = "IN"

                # B. Exit Gate:
                # By default, Lower (BELOW) -> Upper (ABOVE) is an Exit ("OUT").
                # If operator specifically configured counting_direction="down", then ABOVE -> BELOW is "OUT".
                elif is_exit_gate:
                    if cfg_direction == "down":
                        if state.last_stable_region == GateRegion.ABOVE and current_region == GateRegion.BELOW:
                            crossing_event_type = "OUT"
                    else:
                        if state.last_stable_region == GateRegion.BELOW and current_region == GateRegion.ABOVE:
                            crossing_event_type = "OUT"

                # C. Bidirectional / General Gate:
                else:
                    if cfg_direction == "up":
                        if state.last_stable_region == GateRegion.BELOW and current_region == GateRegion.ABOVE:
                            crossing_event_type = "IN"
                        elif state.last_stable_region == GateRegion.ABOVE and current_region == GateRegion.BELOW:
                            crossing_event_type = "OUT"
                    elif cfg_direction == "right":
                        # For vertical line: moving left-to-right is positive side -> negative side
                        if state.last_stable_region == GateRegion.BELOW and current_region == GateRegion.ABOVE:
                            crossing_event_type = "IN"
                        elif state.last_stable_region == GateRegion.ABOVE and current_region == GateRegion.BELOW:
                            crossing_event_type = "OUT"
                    elif cfg_direction == "left":
                        if state.last_stable_region == GateRegion.ABOVE and current_region == GateRegion.BELOW:
                            crossing_event_type = "IN"
                        elif state.last_stable_region == GateRegion.BELOW and current_region == GateRegion.ABOVE:
                            crossing_event_type = "OUT"
                    else:  # "down", "any", "both"
                        if state.last_stable_region == GateRegion.ABOVE and current_region == GateRegion.BELOW:
                            crossing_event_type = "IN"
                        elif state.last_stable_region == GateRegion.BELOW and current_region == GateRegion.ABOVE:
                            crossing_event_type = "OUT"

                # Update the last confirmed stable region
                state.last_stable_region = current_region

                # Validate and emit event
                if crossing_event_type is not None:
                    valid_for_gate = True
                    if is_entry_gate and crossing_event_type != "IN":
                        valid_for_gate = False
                    elif is_exit_gate and crossing_event_type != "OUT":
                        valid_for_gate = False

                    if valid_for_gate and (not state.has_crossed) and (now >= state.cooldown_until):
                        if crossing_event_type == "IN":
                            if self.config.single_pass_only and track_id in self.registered_entered:
                                state.is_blocked = True
                                state.block_reason = "ALREADY ENTERED (PASSBACK DENIED)"
                                state.status_label = "BLOCKED"
                                block_ev = CrossingEvent(
                                    track_id=track_id,
                                    direction="IN",
                                    timestamp=now,
                                    centroid=(person_x, person_y),
                                    confidence=confidence,
                                    is_blocked=True,
                                    block_reason=state.block_reason,
                                )
                                events.append(block_ev)
                                self._pending_events.append(block_ev)
                                self.blocked_violations.append({
                                    "track_id": track_id,
                                    "type": "RE_ENTRY_DENIED",
                                    "timestamp": now,
                                })
                                logger.warning(f"Anti-Passback: Track #{track_id} re-entry blocked")
                            else:
                                self.registered_entered.add(track_id)
                                self.total_in += 1
                                self.last_flash_time = now
                                state.has_crossed = True
                                state.cross_count += 1
                                state.last_crossing_dir = "IN"
                                state.last_crossing_time = now
                                state.cooldown_until = now + self.config.crossing_cooldown
                                state.status_label = "ENTRY EVENT"

                                ev = CrossingEvent(
                                    track_id=track_id,
                                    direction="IN",
                                    timestamp=now,
                                    centroid=(person_x, person_y),
                                    confidence=confidence,
                                )
                                events.append(ev)
                                self._pending_events.append(ev)
                                logger.info(f"Entry counted: Track #{track_id} (ABOVE->BELOW) | Total IN: {self.total_in}")

                        elif crossing_event_type == "OUT":
                            if self.config.single_pass_only and track_id in self.registered_exited:
                                state.is_blocked = True
                                state.block_reason = "ALREADY EXITED (PASSBACK DENIED)"
                                state.status_label = "BLOCKED"
                                block_ev = CrossingEvent(
                                    track_id=track_id,
                                    direction="OUT",
                                    timestamp=now,
                                    centroid=(person_x, person_y),
                                    confidence=confidence,
                                    is_blocked=True,
                                    block_reason=state.block_reason,
                                )
                                events.append(block_ev)
                                self._pending_events.append(block_ev)
                                self.blocked_violations.append({
                                    "track_id": track_id,
                                    "type": "RE_EXIT_DENIED",
                                    "timestamp": now,
                                })
                                logger.warning(f"Anti-Passback: Track #{track_id} re-exit blocked")
                            else:
                                self.registered_exited.add(track_id)
                                self.total_out += 1
                                self.last_flash_time = now
                                state.has_crossed = True
                                state.cross_count += 1
                                state.last_crossing_dir = "OUT"
                                state.last_crossing_time = now
                                state.cooldown_until = now + self.config.crossing_cooldown
                                state.status_label = "EXIT EVENT"

                                ev = CrossingEvent(
                                    track_id=track_id,
                                    direction="OUT",
                                    timestamp=now,
                                    centroid=(person_x, person_y),
                                    confidence=confidence,
                                )
                                events.append(ev)
                                self._pending_events.append(ev)
                                logger.info(f"Exit counted: Track #{track_id} (BELOW->ABOVE) | Total OUT: {self.total_out}")

            # Keep active event badge label visible for 1 second after crossing
            if state.last_crossing_time > 0 and (now - state.last_crossing_time < 1.0):
                if state.last_crossing_dir == "IN":
                    state.status_label = "ENTRY EVENT"
                elif state.last_crossing_dir == "OUT":
                    state.status_label = "EXIT EVENT"
            elif not state.is_blocked:
                state.status_label = current_region.value

            det["region"] = current_region.value
            det["status"] = state.status_label
            det["is_blocked"] = state.is_blocked
            det["has_crossed"] = state.has_crossed
            det["person_x"] = person_x
            det["person_y"] = person_y

        # Expire inactive tracks
        expired = [
            tid for tid, s in self.tracks.items()
            if now - s.last_seen > self.config.track_expiry and tid not in seen_tracks
        ]
        for tid in expired:
            del self.tracks[tid]

        return events

    def cleanup_tracks(self, current_time: float | None = None):
        """Manually remove tracks older than track_expiry."""
        now = current_time or time.time()
        expired = [
            tid for tid, s in self.tracks.items()
            if now - s.last_seen > self.config.track_expiry
        ]
        for tid in expired:
            del self.tracks[tid]

    @property
    def _tracks(self):
        """Compatibility property for test assertions."""
        return self.tracks

    def get_counts(self) -> dict:
        """Return current crossing counts."""
        return {
            "total_in": self.total_in,
            "total_out": self.total_out,
            "active_tracks": len(self.tracks),
            "registered_entered": len(self.registered_entered),
            "registered_exited": len(self.registered_exited),
            "violations": len(self.blocked_violations),
        }

    def drain_events(self) -> list[CrossingEvent]:
        """Return and clear pending events."""
        events = list(self._pending_events)
        self._pending_events.clear()
        return events

    def reset(self):
        """Reset all counts, track state, and anti-passback registry."""
        self.tracks.clear()
        self.registered_entered.clear()
        self.registered_exited.clear()
        self.blocked_violations.clear()
        self.total_in = 0
        self.total_out = 0
        self._pending_events.clear()

    def update_line(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        counting_direction: str | None = None,
    ):
        """Update counting line coordinates dynamically and recompute normal vectors."""
        self.config.start_x = start_x
        self.config.start_y = start_y
        self.config.end_x = end_x
        self.config.end_y = end_y
        if counting_direction:
            self.config.counting_direction = counting_direction
        self._update_line_vector()
