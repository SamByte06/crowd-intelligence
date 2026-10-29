"""
Alert Service — Configurable alerts with thresholds, hysteresis, and cooldown.

Supports: NORMAL, WARNING, CRITICAL, DATA_UNRELIABLE severity levels.
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.venue import Venue
from app.models.alert import Alert, AlertSeverity, AlertStatus
from app.models.audit_log import AuditLog
from app.services.flow_service import FlowRateService
from app.services.forecast_service import ForecastService
from app.config import settings

logger = logging.getLogger(__name__)


class AlertService:
    """Evaluates alert conditions and manages alert lifecycle."""

    @staticmethod
    def evaluate(db: Session, venue_id: str) -> list[Alert]:
        """Evaluate all alert conditions for a venue and create/resolve alerts."""
        venue = db.query(Venue).filter(Venue.id == venue_id).first()
        if not venue:
            return []

        new_alerts = []
        flow = FlowRateService.calculate(db, venue_id)
        forecast_data = ForecastService.forecast(db, venue_id)
        effective_cap = venue.effective_capacity

        # --- Occupancy threshold alerts (Moderate to High & High to Critical) ---
        if effective_cap and effective_cap > 0:
            occupancy_pct = venue.current_occupancy / effective_cap

            # Critical threshold: High to Critical escalation
            if occupancy_pct >= venue.critical_threshold:
                alert = AlertService._create_alert_if_new(
                    db, venue,
                    severity=AlertSeverity.CRITICAL,
                    alert_type_key=f"occupancy_critical_{venue_id}",
                    title="Critical Occupancy Surge: High to Critical",
                    message=(
                        f"Occupancy escalated rapidly to {venue.current_occupancy} "
                        f"({occupancy_pct:.0%} of capacity {effective_cap}). "
                        f"Critical threshold ({venue.critical_threshold:.0%}) exceeded."
                    ),
                    recommended_action=(
                        "Immediately restrict incoming flow. Verify all emergency and auxiliary exits are open. "
                        "Deploy marshals to prevent bottlenecking."
                    ),
                    flow=flow,
                    forecast_data=forecast_data,
                )
                if alert:
                    new_alerts.append(alert)

            # Warning threshold: Moderate to High escalation
            elif occupancy_pct >= venue.warning_threshold:
                alert = AlertService._create_alert_if_new(
                    db, venue,
                    severity=AlertSeverity.WARNING,
                    alert_type_key=f"occupancy_warning_{venue_id}",
                    title="Rapid Crowd Surge: Moderate to High",
                    message=(
                        f"Crowd escalated to {venue.current_occupancy} "
                        f"({occupancy_pct:.0%} of capacity {effective_cap}). "
                        f"High crowd threshold ({venue.warning_threshold:.0%}) reached."
                    ),
                    recommended_action=(
                        "Monitor entry gate influx closely. Prepare queue management barriers "
                        "and divert incoming pedestrian flow."
                    ),
                    flow=flow,
                    forecast_data=forecast_data,
                )
                if alert:
                    new_alerts.append(alert)

            # Forecast early warning: Approaching High/Critical threshold rapidly
            if forecast_data.get("time_to_warning_minutes") is not None:
                ttw = forecast_data["time_to_warning_minutes"]
                if ttw <= 10 and occupancy_pct < venue.warning_threshold and flow.get("net_inflow_per_min", 0) > 10:
                    alert = AlertService._create_alert_if_new(
                        db, venue,
                        severity=AlertSeverity.WARNING,
                        alert_type_key=f"forecast_warning_{venue_id}",
                        title="Rapid Inflow Surge: Approaching High Capacity",
                        message=(
                            f"At rapid inflow rate ({flow['net_inflow_per_min']:.1f}/min), "
                            f"occupancy is projected to surge into High territory in ~{ttw:.0f} minutes."
                        ),
                        recommended_action="Prepare entry throttling before high crowd congestion occurs.",
                        flow=flow,
                        forecast_data=forecast_data,
                    )
                    if alert:
                        new_alerts.append(alert)

        # Auto-resolve alerts whose conditions are no longer met
        AlertService._auto_resolve_stale_alerts(db, venue, effective_cap)

        db.commit()
        return new_alerts

    @staticmethod
    def _create_alert_if_new(
        db: Session,
        venue: Venue,
        severity: AlertSeverity,
        alert_type_key: str,
        title: str,
        message: str,
        recommended_action: str,
        flow: dict,
        forecast_data: dict,
    ) -> Optional[Alert]:
        """Create an alert if one isn't already active (with cooldown)."""
        now = datetime.now(timezone.utc)

        # Check for existing active/acknowledged alert of same type
        existing = (
            db.query(Alert)
            .filter(
                Alert.venue_id == venue.id,
                Alert.alert_type_key == alert_type_key,
                Alert.status.in_([AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]),
            )
            .first()
        )
        if existing:
            return None

        # Check cooldown
        recent = (
            db.query(Alert)
            .filter(
                Alert.venue_id == venue.id,
                Alert.alert_type_key == alert_type_key,
                Alert.cooldown_until != None,  # noqa: E711
                Alert.cooldown_until > now,
            )
            .first()
        )
        if recent:
            return None

        cooldown_until = now + timedelta(seconds=settings.ALERT_COOLDOWN_SECONDS)

        alert = Alert(
            id=str(uuid.uuid4()),
            venue_id=venue.id,
            severity=severity,
            title=title,
            message=message,
            recommended_action=recommended_action,
            occupancy_at_trigger=venue.current_occupancy,
            capacity_at_trigger=venue.effective_capacity,
            entry_rate_at_trigger=flow.get("entry_rate_per_min"),
            exit_rate_at_trigger=flow.get("exit_rate_per_min"),
            forecast_occupancy=forecast_data.get("forecasts", [{}])[0].get("forecast_occupancy") if forecast_data.get("forecasts") else None,
            trigger_reason=alert_type_key,
            alert_type_key=alert_type_key,
            cooldown_until=cooldown_until,
        )
        db.add(alert)
        logger.info(f"Alert created: {severity.value} - {title} for venue {venue.id}")
        return alert

    @staticmethod
    def _auto_resolve_stale_alerts(db: Session, venue: Venue, effective_cap):
        """Auto-resolve alerts whose conditions are no longer met."""
        if not effective_cap or effective_cap <= 0:
            return

        now = datetime.now(timezone.utc)
        occupancy_pct = venue.current_occupancy / effective_cap

        # Resolve occupancy warnings if below threshold
        if occupancy_pct < venue.warning_threshold:
            stale = (
                db.query(Alert)
                .filter(
                    Alert.venue_id == venue.id,
                    Alert.alert_type_key.like(f"occupancy_%_{venue.id}"),
                    Alert.status.in_([AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]),
                )
                .all()
            )
            for a in stale:
                a.status = AlertStatus.RESOLVED
                a.resolved_at = now
                a.resolved_by = "system"
                a.resolution_note = "Condition no longer met"

        # Resolve negative occupancy alert if occupancy is now non-negative
        if venue.current_occupancy >= 0:
            neg_alerts = (
                db.query(Alert)
                .filter(
                    Alert.venue_id == venue.id,
                    Alert.alert_type_key == f"reconciliation_negative_{venue.id}",
                    Alert.status.in_([AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]),
                )
                .all()
            )
            for a in neg_alerts:
                a.status = AlertStatus.RESOLVED
                a.resolved_at = now
                a.resolved_by = "system"
                a.resolution_note = "Occupancy reconciled to non-negative"

        # Resolve any noisy non-escalation alerts (flow imbalance or data quality)
        noisy_alerts = (
            db.query(Alert)
            .filter(
                Alert.venue_id == venue.id,
                Alert.alert_type_key.in_([
                    f"flow_imbalance_{venue.id}",
                    f"data_quality_{venue.id}",
                ]),
                Alert.status.in_([AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]),
            )
            .all()
        )
        for a in noisy_alerts:
            a.status = AlertStatus.RESOLVED
            a.resolved_at = now
            a.resolved_by = "system"
            a.resolution_note = "Suppressed to focus on rapid crowd surge escalations"

    @staticmethod
    def acknowledge(db: Session, alert_id: str, acknowledged_by: str = "admin") -> Alert:
        """Acknowledge an alert."""
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            raise ValueError(f"Alert {alert_id} not found")
        if alert.status != AlertStatus.ACTIVE:
            raise ValueError(f"Alert {alert_id} is not active (status={alert.status})")

        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = datetime.now(timezone.utc)
        alert.acknowledged_by = acknowledged_by

        db.add(AuditLog(
            venue_id=alert.venue_id,
            action="alert_acknowledged",
            entity_type="alert",
            entity_id=alert_id,
            performed_by=acknowledged_by,
        ))
        db.commit()
        db.refresh(alert)
        return alert

    @staticmethod
    def resolve(db: Session, alert_id: str, resolved_by: str = "admin",
                resolution_note: str | None = None) -> Alert:
        """Resolve an alert."""
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            raise ValueError(f"Alert {alert_id} not found")
        if alert.status == AlertStatus.RESOLVED:
            raise ValueError(f"Alert {alert_id} is already resolved")

        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now(timezone.utc)
        alert.resolved_by = resolved_by
        alert.resolution_note = resolution_note

        db.add(AuditLog(
            venue_id=alert.venue_id,
            action="alert_resolved",
            entity_type="alert",
            entity_id=alert_id,
            performed_by=resolved_by,
            details={"note": resolution_note},
        ))
        db.commit()
        db.refresh(alert)
        return alert

    @staticmethod
    def get_active_alerts(db: Session, venue_id: str) -> list[Alert]:
        """Get all active and acknowledged alerts for a venue."""
        return (
            db.query(Alert)
            .filter(
                Alert.venue_id == venue_id,
                Alert.status.in_([AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]),
            )
            .order_by(Alert.triggered_at.desc())
            .all()
        )

    @staticmethod
    def get_alert_history(db: Session, venue_id: str, limit: int = 50) -> list[Alert]:
        """Get alert history for a venue."""
        return (
            db.query(Alert)
            .filter(Alert.venue_id == venue_id)
            .order_by(Alert.triggered_at.desc())
            .limit(limit)
            .all()
        )
