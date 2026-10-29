"""
Flow Rate Service — Calculates entry, exit, and net flow rates over configurable windows.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.counting_event import CountingEvent, CrossingDirection
from app.config import settings

logger = logging.getLogger(__name__)


class FlowRateService:
    """Calculates flow rates from the counting event ledger."""

    @staticmethod
    def calculate(db: Session, venue_id: str,
                  window_seconds: int | None = None) -> dict:
        """
        Calculate entry/exit/net flow rates for a venue over a time window.

        Returns rates in events per minute.
        """
        window = window_seconds or settings.FLOW_WINDOW_SECONDS
        now = datetime.now(timezone.utc)
        since = now - timedelta(seconds=window)

        # Count entries in window
        entries = (
            db.query(func.count(CountingEvent.id))
            .filter(
                CountingEvent.venue_id == venue_id,
                CountingEvent.direction == CrossingDirection.IN,
                CountingEvent.timestamp >= since,
            )
            .scalar() or 0
        )

        # Count exits in window
        exits = (
            db.query(func.count(CountingEvent.id))
            .filter(
                CountingEvent.venue_id == venue_id,
                CountingEvent.direction == CrossingDirection.OUT,
                CountingEvent.timestamp >= since,
            )
            .scalar() or 0
        )

        window_minutes = window / 60.0
        entry_rate = entries / window_minutes if window_minutes > 0 else 0
        exit_rate = exits / window_minutes if window_minutes > 0 else 0
        net_inflow = entry_rate - exit_rate

        # If strict default window had a momentary lull, check 3-minute window for active rate
        if window_seconds is None and entries == 0 and exits == 0:
            since_wider = now - timedelta(seconds=180)
            entries_w = (
                db.query(func.count(CountingEvent.id))
                .filter(
                    CountingEvent.venue_id == venue_id,
                    CountingEvent.direction == CrossingDirection.IN,
                    CountingEvent.timestamp >= since_wider,
                )
                .scalar() or 0
            )
            exits_w = (
                db.query(func.count(CountingEvent.id))
                .filter(
                    CountingEvent.venue_id == venue_id,
                    CountingEvent.direction == CrossingDirection.OUT,
                    CountingEvent.timestamp >= since_wider,
                )
                .scalar() or 0
            )
            if entries_w > 0 or exits_w > 0:
                entry_rate = round(entries_w / 3.0, 2)
                exit_rate = round(exits_w / 3.0, 2)
                net_inflow = round(entry_rate - exit_rate, 2)
                entries = entries_w
                exits = exits_w
                window = 180

        return {
            "venue_id": venue_id,
            "window_seconds": window,
            "entry_rate_per_min": round(entry_rate, 2),
            "exit_rate_per_min": round(exit_rate, 2),
            "net_inflow_per_min": round(net_inflow, 2),
            "total_entries_in_window": entries,
            "total_exits_in_window": exits,
            "measured_at": now,
        }

    @staticmethod
    def get_rates_multi_window(db: Session, venue_id: str) -> dict:
        """Calculate flow rates for multiple windows (1, 5, 15 min)."""
        return {
            "1min": FlowRateService.calculate(db, venue_id, 60),
            "5min": FlowRateService.calculate(db, venue_id, 300),
            "15min": FlowRateService.calculate(db, venue_id, 900),
        }
