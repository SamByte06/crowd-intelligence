"""
Monitoring API endpoints — Occupancy, flow, forecast, alerts, events.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database import get_db
from app.models.venue import Venue
from app.models.counting_event import CountingEvent
from app.models.alert import Alert
from app.schemas.occupancy import (
    OccupancyResponse, FlowRateResponse, ForecastResponse, ForecastPoint,
    GateCountResponse, EventResponse,
)
from app.schemas.alert import AlertResponse, AlertAcknowledge, AlertResolve
from app.services.occupancy_service import OccupancyService
from app.services.flow_service import FlowRateService
from app.services.forecast_service import ForecastService
from app.services.alert_service import AlertService
from app.services.camera_manager import camera_manager

router = APIRouter(tags=["Monitoring"])


@router.get("/venues/{venue_id}/occupancy", response_model=OccupancyResponse)
def get_occupancy(venue_id: str, db: Session = Depends(get_db)):
    """Get current occupancy for a venue."""
    try:
        data = OccupancyService.get_occupancy(db, venue_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return OccupancyResponse(**data)


@router.get("/venues/{venue_id}/flow", response_model=FlowRateResponse)
def get_flow(venue_id: str, window: int = Query(60, ge=10, le=3600), db: Session = Depends(get_db)):
    """Get flow rates for a venue."""
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    data = FlowRateService.calculate(db, venue_id, window)
    return FlowRateResponse(**data)


@router.get("/venues/{venue_id}/forecast", response_model=ForecastResponse)
def get_forecast(venue_id: str, db: Session = Depends(get_db)):
    """Get occupancy forecasts for a venue."""
    try:
        data = ForecastService.forecast(db, venue_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ForecastResponse(
        venue_id=data["venue_id"],
        current_occupancy=data["current_occupancy"],
        net_inflow_rate=data["net_inflow_rate"],
        effective_capacity=data["effective_capacity"],
        time_to_warning_minutes=data["time_to_warning_minutes"],
        time_to_critical_minutes=data["time_to_critical_minutes"],
        time_to_capacity_minutes=data["time_to_capacity_minutes"],
        forecasts=[ForecastPoint(**f) for f in data["forecasts"]],
        data_quality=data["data_quality"],
        measured_at=data["measured_at"],
    )


@router.get("/venues/{venue_id}/alerts", response_model=list[AlertResponse])
def get_alerts(
    venue_id: str,
    include_resolved: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Get alerts for a venue."""
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    if include_resolved:
        alerts = AlertService.get_alert_history(db, venue_id, limit)
    else:
        alerts = AlertService.get_active_alerts(db, venue_id)
    return [AlertResponse.model_validate(a) for a in alerts]


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertResponse)
def acknowledge_alert(alert_id: str, data: AlertAcknowledge, db: Session = Depends(get_db)):
    """Acknowledge an alert."""
    try:
        alert = AlertService.acknowledge(db, alert_id, data.acknowledged_by)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return AlertResponse.model_validate(alert)


@router.post("/alerts/{alert_id}/resolve", response_model=AlertResponse)
def resolve_alert(alert_id: str, data: AlertResolve, db: Session = Depends(get_db)):
    """Resolve an alert."""
    try:
        alert = AlertService.resolve(db, alert_id, data.resolved_by, data.resolution_note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return AlertResponse.model_validate(alert)


@router.get("/venues/{venue_id}/events", response_model=list[EventResponse])
def get_events(
    venue_id: str,
    limit: int = Query(100, ge=1, le=1000),
    gate_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Get counting events for a venue."""
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    query = db.query(CountingEvent).filter(CountingEvent.venue_id == venue_id)
    if gate_id:
        query = query.filter(CountingEvent.gate_id == gate_id)
    events = query.order_by(CountingEvent.timestamp.desc()).limit(limit).all()
    return [EventResponse.model_validate(e) for e in events]


@router.get("/venues/{venue_id}/gate-counts", response_model=list[GateCountResponse])
def get_gate_counts(venue_id: str, db: Session = Depends(get_db)):
    """Get per-gate entry/exit counts."""
    from app.models.gate import Gate
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    gates = db.query(Gate).filter(Gate.venue_id == venue_id).all()
    return [
        GateCountResponse(
            gate_id=g.id,
            display_name=g.display_name,
            gate_type=g.gate_type.value,
            entry_count=g.entry_count,
            exit_count=g.exit_count,
            status=g.status.value,
        )
        for g in gates
    ]


@router.get("/venues/{venue_id}/snapshots")
def get_snapshots(
    venue_id: str,
    minutes: int = Query(60, ge=1, le=1440),
    db: Session = Depends(get_db),
):
    """Get historical occupancy snapshots."""
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    snapshots = OccupancyService.get_snapshots(db, venue_id, minutes)
    return [
        {
            "timestamp": s.timestamp.isoformat() if s.timestamp else None,
            "occupancy": s.occupancy,
            "entry_rate": s.entry_rate,
            "exit_rate": s.exit_rate,
            "net_inflow": s.net_inflow,
            "capacity_utilization": s.capacity_utilization,
        }
        for s in snapshots
    ]


@router.get("/cameras/health")
def get_camera_health():
    """Get health status for all active cameras."""
    return camera_manager.get_health()


@router.get("/venues/{venue_id}/dashboard")
def get_dashboard(venue_id: str, db: Session = Depends(get_db)):
    """Get complete aggregated dashboard state for a venue."""
    from app.api.v1.websocket import _get_venue_state
    state = _get_venue_state(venue_id)
    if not state:
        raise HTTPException(status_code=404, detail="Venue not found")
    return state


from pydantic import BaseModel

class PushSubscriptionPayload(BaseModel):
    venue_id: str
    subscription: dict

class PushTestPayload(BaseModel):
    venue_id: str


@router.get("/push/vapid-public-key")
def get_push_public_key():
    """Return the VAPID applicationServerKey for browser push subscription."""
    from app.services.push_service import get_vapid_public_key
    return {"publicKey": get_vapid_public_key()}


@router.post("/push/subscribe")
def subscribe_push(payload: PushSubscriptionPayload):
    """Register browser push subscription for a venue."""
    from app.services.push_service import add_subscription
    add_subscription(payload.venue_id, payload.subscription)
    return {"status": "subscribed"}


@router.post("/push/test")
def test_push(payload: PushTestPayload, db: Session = Depends(get_db)):
    """Trigger an immediate real native Web Push directly through Google FCM/WNS."""
    from app.services.push_service import broadcast_web_push
    venue = db.query(Venue).filter(Venue.id == payload.venue_id).first()
    venue_name = venue.name if venue else "Monitored Event"
    broadcast_web_push(
        venue_id=payload.venue_id,
        title=f"🔔 Native Phone Push Alert • {venue_name}",
        body="Real background Web Push is active! You will receive this alert even if you are on Instagram or your phone is locked.",
        severity="WARNING",
        tag="test-push",
    )
    return {"status": "dispatched"}

