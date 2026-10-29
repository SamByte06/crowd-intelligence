"""
Occupancy Service — Central venue occupancy state management.

Implements: current_occupancy = initial_occupancy + confirmed_entries - confirmed_exits
with an auditable event ledger and baseline reconciliation.
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.venue import Venue
from app.models.gate import Gate, GateType
from app.models.counting_event import CountingEvent, CrossingDirection
from app.models.occupancy import OccupancyBaseline, OccupancySnapshot
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


class OccupancyService:
    """Manages venue occupancy calculations and persistence."""

    @staticmethod
    def set_baseline(db: Session, venue_id: str, occupancy: int,
                     established_by: str = "admin", reason: str | None = None) -> Venue:
        """Establish or reset the occupancy baseline."""
        venue = db.query(Venue).filter(Venue.id == venue_id).first()
        if not venue:
            raise ValueError(f"Venue {venue_id} not found")

        if occupancy < 0:
            raise ValueError("Baseline occupancy cannot be negative")

        # Record baseline
        baseline = OccupancyBaseline(
            venue_id=venue_id,
            occupancy_value=occupancy,
            established_by=established_by,
            reason=reason or "Initial baseline",
        )
        db.add(baseline)

        # Update venue
        venue.current_occupancy = occupancy
        venue.total_entries = 0
        venue.total_exits = 0
        venue.baseline_established = True
        venue.baseline_established_at = datetime.now(timezone.utc)
        venue.baseline_established_by = established_by

        # Audit
        db.add(AuditLog(
            venue_id=venue_id,
            action="baseline_set",
            entity_type="venue",
            entity_id=venue_id,
            performed_by=established_by,
            details={"occupancy": occupancy, "reason": reason},
        ))

        db.commit()
        db.refresh(venue)
        logger.info(f"Baseline set for venue {venue_id}: occupancy={occupancy}")
        return venue

    @staticmethod
    def record_crossing(db: Session, venue_id: str, gate_id: str,
                        direction: str, track_id: int | None = None,
                        confidence: float | None = None,
                        timestamp: datetime | None = None) -> CountingEvent:
        """Record a confirmed line-crossing event and update occupancy."""
        venue = db.query(Venue).filter(Venue.id == venue_id).first()
        if not venue:
            raise ValueError(f"Venue {venue_id} not found")

        gate = db.query(Gate).filter(Gate.id == gate_id).first()
        if not gate:
            raise ValueError(f"Gate {gate_id} not found")

        crossing_dir = CrossingDirection.IN if direction == "IN" else CrossingDirection.OUT

        event = CountingEvent(
            id=str(uuid.uuid4()),
            venue_id=venue_id,
            gate_id=gate_id,
            direction=crossing_dir,
            track_id=track_id,
            confidence=confidence,
            timestamp=timestamp or datetime.now(timezone.utc),
        )
        db.add(event)

        # Update gate count
        if crossing_dir == CrossingDirection.IN:
            gate.entry_count += 1
        else:
            gate.exit_count += 1

        gate.last_count_at = datetime.now(timezone.utc)

        # Get latest baseline
        latest_baseline = (
            db.query(OccupancyBaseline)
            .filter(OccupancyBaseline.venue_id == venue_id)
            .order_by(OccupancyBaseline.timestamp.desc())
            .first()
        )
        base_val = latest_baseline.occupancy_value if latest_baseline else 0

        # Synchronize global venue counts strictly as sum of gates:
        gates = db.query(Gate).filter(Gate.venue_id == venue_id).all()
        entry_gates = [g for g in gates if (g.gate_type == GateType.ENTRY or str(g.gate_type).endswith("ENTRY"))]
        exit_gates = [g for g in gates if (g.gate_type == GateType.EXIT or str(g.gate_type).endswith("EXIT"))]

        if entry_gates:
            total_in = sum(g.entry_count or 0 for g in entry_gates)
        else:
            total_in = sum(g.entry_count or 0 for g in gates)

        if exit_gates:
            total_out = sum(g.exit_count or 0 for g in exit_gates)
        else:
            total_out = sum(g.exit_count or 0 for g in gates)

        venue.total_entries = total_in
        venue.total_exits = total_out
        venue.current_occupancy = max(0, base_val + total_in - total_out)

        db.commit()
        db.refresh(event)
        return event

    @staticmethod
    def get_occupancy(db: Session, venue_id: str) -> dict:
        """Get current occupancy state for a venue."""
        venue = db.query(Venue).filter(Venue.id == venue_id).first()
        if not venue:
            raise ValueError(f"Venue {venue_id} not found")

        # Derive strictly from all gates for guaranteed synchronization
        gates = db.query(Gate).filter(Gate.venue_id == venue_id).all()
        entry_gates = [g for g in gates if (g.gate_type == GateType.ENTRY or str(g.gate_type).endswith("ENTRY"))]
        exit_gates = [g for g in gates if (g.gate_type == GateType.EXIT or str(g.gate_type).endswith("EXIT"))]

        if gates:
            latest_baseline = (
                db.query(OccupancyBaseline)
                .filter(OccupancyBaseline.venue_id == venue_id)
                .order_by(OccupancyBaseline.timestamp.desc())
                .first()
            )
            base_val = latest_baseline.occupancy_value if latest_baseline else 0
            if entry_gates:
                total_in = sum(g.entry_count or 0 for g in entry_gates)
            else:
                total_in = sum(g.entry_count or 0 for g in gates)

            if exit_gates:
                total_out = sum(g.exit_count or 0 for g in exit_gates)
            else:
                total_out = sum(g.exit_count or 0 for g in gates)

            safe_occupancy = max(0, base_val + total_in - total_out)

            # Ensure database is aligned
            if venue.total_entries != total_in or venue.total_exits != total_out or venue.current_occupancy != safe_occupancy:
                venue.total_entries = total_in
                venue.total_exits = total_out
                venue.current_occupancy = safe_occupancy
                db.commit()
        else:
            safe_occupancy = max(0, venue.current_occupancy)
            if venue.current_occupancy < 0:
                venue.current_occupancy = 0
                db.commit()

        effective_cap = venue.effective_capacity
        remaining = None
        pct = None

        if effective_cap and effective_cap > 0:
            remaining = max(0, effective_cap - safe_occupancy)
            pct = round((safe_occupancy / effective_cap) * 100, 1)

        is_uncertain = not venue.baseline_established

        return {
            "venue_id": venue.id,
            "current_occupancy": safe_occupancy,
            "effective_capacity": effective_cap,
            "capacity_is_estimated": venue.capacity_is_estimated,
            "remaining_capacity": remaining,
            "occupancy_percentage": pct,
            "total_entries": venue.total_entries,
            "total_exits": venue.total_exits,
            "baseline_established": venue.baseline_established,
            "occupancy_is_uncertain": is_uncertain,
            "reconciliation_needed": False,
            "last_updated": datetime.now(timezone.utc),
        }

    @staticmethod
    def reconcile(db: Session, venue_id: str, verified_occupancy: int,
                  performed_by: str = "admin", reason: str = "") -> Venue:
        """Reconcile occupancy with a verified manual count."""
        venue = db.query(Venue).filter(Venue.id == venue_id).first()
        if not venue:
            raise ValueError(f"Venue {venue_id} not found")

        old_occupancy = venue.current_occupancy
        delta = verified_occupancy - old_occupancy

        venue.current_occupancy = verified_occupancy

        # Record as a new baseline
        baseline = OccupancyBaseline(
            venue_id=venue_id,
            occupancy_value=verified_occupancy,
            established_by=performed_by,
            reason=f"Reconciliation: {reason}. Previous={old_occupancy}, Delta={delta}",
        )
        db.add(baseline)

        # Audit
        db.add(AuditLog(
            venue_id=venue_id,
            action="occupancy_reconciled",
            entity_type="venue",
            entity_id=venue_id,
            performed_by=performed_by,
            details={
                "old_occupancy": old_occupancy,
                "new_occupancy": verified_occupancy,
                "delta": delta,
                "reason": reason,
            },
        ))

        db.commit()
        db.refresh(venue)
        logger.info(
            f"Occupancy reconciled for venue {venue_id}: "
            f"{old_occupancy} -> {verified_occupancy} (delta={delta})"
        )
        return venue

    @staticmethod
    def save_snapshot(db: Session, venue_id: str, entry_rate: float = 0,
                      exit_rate: float = 0, net_inflow: float = 0):
        """Save a periodic occupancy snapshot for time-series data."""
        venue = db.query(Venue).filter(Venue.id == venue_id).first()
        if not venue:
            return

        cap = venue.effective_capacity
        utilization = None
        if cap and cap > 0:
            utilization = round((venue.current_occupancy / cap) * 100, 1)

        snapshot = OccupancySnapshot(
            venue_id=venue_id,
            occupancy=venue.current_occupancy,
            total_entries=venue.total_entries,
            total_exits=venue.total_exits,
            entry_rate=entry_rate,
            exit_rate=exit_rate,
            net_inflow=net_inflow,
            capacity_utilization=utilization,
        )
        db.add(snapshot)
        db.commit()

    @staticmethod
    def get_snapshots(db: Session, venue_id: str, minutes: int = 60) -> list[OccupancySnapshot]:
        """Get recent occupancy snapshots."""
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        return (
            db.query(OccupancySnapshot)
            .filter(
                OccupancySnapshot.venue_id == venue_id,
                OccupancySnapshot.timestamp >= since,
            )
            .order_by(OccupancySnapshot.timestamp.asc())
            .all()
        )
