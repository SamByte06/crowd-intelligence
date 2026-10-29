"""
Forecast Service — Projects future occupancy based on current flow rates.

Handles zero, positive, and negative net inflow safely. Marks data quality
when cameras are degraded or data is insufficient.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.venue import Venue
from app.models.gate import Gate, GateStatus
from app.services.flow_service import FlowRateService
from app.config import settings

logger = logging.getLogger(__name__)


class ForecastService:
    """Projects future occupancy and time-to-threshold estimates."""

    @staticmethod
    def forecast(db: Session, venue_id: str) -> dict:
        """
        Generate occupancy forecasts for configured horizons.

        Uses: forecast_occupancy(h) = current_occupancy + net_inflow_rate * h
        """
        venue = db.query(Venue).filter(Venue.id == venue_id).first()
        if not venue:
            raise ValueError(f"Venue {venue_id} not found")

        flow = FlowRateService.calculate(db, venue_id)
        net_inflow = flow["net_inflow_per_min"]
        current = venue.current_occupancy
        effective_cap = venue.effective_capacity

        # Assess data quality
        data_quality = ForecastService._assess_data_quality(db, venue)

        # Calculate forecasts for each horizon
        horizons = settings.forecast_horizons_list
        forecasts = []
        for h in horizons:
            projected = current + int(net_inflow * h)
            projected = max(0, projected)  # Floor at 0 but don't hide it

            point = {
                "horizon_minutes": h,
                "forecast_occupancy": projected,
                "is_above_warning": False,
                "is_above_critical": False,
                "is_above_capacity": False,
            }

            if effective_cap and effective_cap > 0:
                warning_level = int(effective_cap * venue.warning_threshold)
                critical_level = int(effective_cap * venue.critical_threshold)
                point["is_above_warning"] = projected >= warning_level
                point["is_above_critical"] = projected >= critical_level
                point["is_above_capacity"] = projected >= effective_cap

            forecasts.append(point)

        # Time-to-threshold calculations
        time_to_warning = None
        time_to_critical = None
        time_to_capacity = None

        if effective_cap and effective_cap > 0:
            if current >= effective_cap:
                time_to_capacity = 0.0
            elif net_inflow > 0:
                warning_level = int(effective_cap * venue.warning_threshold)
                critical_level = int(effective_cap * venue.critical_threshold)

                if current < warning_level:
                    time_to_warning = round((warning_level - current) / net_inflow, 1)
                if current < critical_level:
                    time_to_critical = round((critical_level - current) / net_inflow, 1)
                time_to_capacity = round((effective_cap - current) / net_inflow, 1)

        return {
            "venue_id": venue_id,
            "current_occupancy": current,
            "net_inflow_rate": net_inflow,
            "effective_capacity": effective_cap,
            "time_to_warning_minutes": time_to_warning,
            "time_to_critical_minutes": time_to_critical,
            "time_to_capacity_minutes": time_to_capacity,
            "forecasts": forecasts,
            "data_quality": data_quality,
            "measured_at": datetime.now(timezone.utc),
        }

    @staticmethod
    def _assess_data_quality(db: Session, venue: Venue) -> str:
        """
        Assess data quality based on camera health.

        Returns: "good", "degraded", or "insufficient"
        """
        gates = db.query(Gate).filter(
            Gate.venue_id == venue.id,
            Gate.is_enabled == True,  # noqa: E712
        ).all()

        if not gates:
            return "insufficient"

        active_count = sum(1 for g in gates if g.status == GateStatus.ACTIVE)
        total = len(gates)

        if active_count == 0:
            return "insufficient"
        if active_count < total:
            return "degraded"
        return "good"
