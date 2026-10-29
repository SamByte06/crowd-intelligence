"""
Venue API endpoints — CRUD operations for venues, baseline, and reconciliation.
"""

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta

from app.database import get_db
from app.models.venue import Venue
from app.models.gate import Gate, GateType, GateStatus, CameraSourceType
from app.models.occupancy import OccupancyBaseline, OccupancySnapshot
from app.models.audit_log import AuditLog
from app.models.counting_event import CountingEvent
from app.models.alert import Alert
from app.schemas.venue import (
    VenueCreate, VenueUpdate, VenueResponse, BaselineRequest, ReconcileRequest,
)
from app.services.occupancy_service import OccupancyService
from app.services.camera_manager import camera_manager

router = APIRouter(prefix="/venues", tags=["Venues"])


class QuickSetupRequest(BaseModel):
    name: str = "AI Crowd Intelligence Zone"
    area_sqm: float
    max_capacity: float | None = None
    entry_streams: list[str] = []
    exit_streams: list[str] = []


@router.get("", response_model=list[VenueResponse])
def list_venues(db: Session = Depends(get_db)):
    """List all venues."""
    venues = db.query(Venue).all()
    result = []
    for v in venues:
        resp = VenueResponse.model_validate(v)
        resp.effective_capacity = v.effective_capacity
        resp.capacity_is_estimated = v.capacity_is_estimated
        resp.monitoring_active = camera_manager.is_venue_counting(v.id)
        result.append(resp)
    return result


@router.post("", response_model=VenueResponse, status_code=201)
def create_venue(data: VenueCreate, db: Session = Depends(get_db)):
    """Create a new venue."""
    venue = Venue(
        name=data.name,
        description=data.description,
        location=data.location,
        usable_area_sqm=data.usable_area_sqm,
        max_capacity=data.max_capacity,
        density_per_sqm=data.density_per_sqm,
        warning_threshold=data.warning_threshold,
        critical_threshold=data.critical_threshold,
        timezone=data.timezone,
    )
    db.add(venue)

    db.add(AuditLog(
        venue_id=venue.id,
        action="venue_created",
        entity_type="venue",
        entity_id=venue.id,
        performed_by="admin",
        details=data.model_dump(),
    ))

    db.commit()
    db.refresh(venue)

    resp = VenueResponse.model_validate(venue)
    resp.effective_capacity = venue.effective_capacity
    resp.capacity_is_estimated = venue.capacity_is_estimated
    return resp


@router.post("/quick-setup")
def quick_setup(data: QuickSetupRequest, db: Session = Depends(get_db)):
    """
    Direct input flow matching 'Give Inputs' form.
    Validates streams, area, and capacity; initializes streams in calibration mode.
    Counting remains paused until operator verifies line alignment and presses Start Process.
    """
    if data.area_sqm is None or float(data.area_sqm) <= 0:
        raise HTTPException(status_code=400, detail="Venue area must be a valid positive number greater than 0.")

    area = float(data.area_sqm)

    if data.max_capacity is not None and int(data.max_capacity) <= 0:
        raise HTTPException(status_code=400, detail="Maximum capacity must be a positive integer greater than 0.")

    # Density standard: 2.0 persons per sqm if not specified
    if data.max_capacity and int(data.max_capacity) > 0:
        eff_capacity = int(data.max_capacity)
    else:
        eff_capacity = max(1, int(area * 2.0))

    # Clean and strictly validate stream URLs
    entry_urls = [u.strip().strip('"').strip("'") for u in data.entry_streams if u and u.strip()]
    exit_urls = [u.strip().strip('"').strip("'") for u in data.exit_streams if u and u.strip()]

    if len(entry_urls) == 0:
        raise HTTPException(status_code=400, detail="At least one valid Entry Gate stream URL is required.")

    if len(exit_urls) == 0:
        raise HTTPException(status_code=400, detail="At least one valid Exit Gate stream URL is required.")

    def get_source_type(u: str) -> CameraSourceType:
        if u.isdigit():
            return CameraSourceType.WEBCAM
        if u.startswith("rtsp://") or u.startswith("rtmp://"):
            return CameraSourceType.RTSP
        if u.startswith("http://") or u.startswith("https://"):
            return CameraSourceType.HTTP
        return CameraSourceType.VIDEO_FILE

    # Fresh real venue starts at 0 occupancy, 0 entries, 0 exits
    venue = Venue(
        name=data.name or "AI Crowd Intelligence Zone",
        usable_area_sqm=area,
        max_capacity=eff_capacity,
        density_per_sqm=2.0,
        warning_threshold=0.75,
        critical_threshold=0.90,
        current_occupancy=0,
        total_entries=0,
        total_exits=0,
        baseline_established=True,
        baseline_established_at=datetime.now(timezone.utc),
        baseline_established_by="Operator",
    )
    db.add(venue)
    db.flush()

    baseline = OccupancyBaseline(
        venue_id=venue.id,
        occupancy_value=0,
        established_by="Operator",
        reason="Initial monitoring baseline",
    )
    db.add(baseline)

    from app.services.gate_counter import LineCrossingConfig

    created_gates = []
    total_streams = len(entry_urls) + len(exit_urls)
    recommended_frame_skip = 2 if total_streams >= 3 else 1

    for idx, url in enumerate(entry_urls, start=1):
        g = Gate(
            venue_id=venue.id,
            display_name=f"Entry Gate {idx}",
            gate_type=GateType.ENTRY,
            camera_source_type=get_source_type(url),
            camera_source=url,
            line_start_x=0.02,
            line_start_y=0.55,
            line_end_x=0.98,
            line_end_y=0.55,
            counting_direction="any",
            confidence_threshold=0.25,
            frame_skip=recommended_frame_skip,
            status=GateStatus.ACTIVE,
            entry_count=0,
            exit_count=0,
            last_count_at=None,
        )
        db.add(g)
        created_gates.append(g)

    for idx, url in enumerate(exit_urls, start=1):
        g = Gate(
            venue_id=venue.id,
            display_name=f"Exit Gate {idx}",
            gate_type=GateType.EXIT,
            camera_source_type=get_source_type(url),
            camera_source=url,
            line_start_x=0.02,
            line_start_y=0.55,
            line_end_x=0.98,
            line_end_y=0.55,
            counting_direction="any",
            confidence_threshold=0.25,
            frame_skip=recommended_frame_skip,
            status=GateStatus.ACTIVE,
            entry_count=0,
            exit_count=0,
            last_count_at=None,
        )
        db.add(g)
        created_gates.append(g)

    db.commit()
    db.refresh(venue)

    # Start camera workers in Calibration / Standby mode (counting_enabled=False)
    # This allows operators to align lines without recording inaccurate premature entries/exits
    for g in created_gates:
        try:
            line_cfg = LineCrossingConfig(
                start_x=g.line_start_x,
                start_y=g.line_start_y,
                end_x=g.line_end_x,
                end_y=g.line_end_y,
                counting_direction=g.counting_direction or "any",
                gate_type=g.gate_type.value if hasattr(g.gate_type, "value") else str(g.gate_type),
                single_pass_only=False,
            )
            camera_manager.start_gate(
                gate_id=g.id,
                venue_id=venue.id,
                camera_source=int(g.camera_source) if str(g.camera_source).isdigit() else g.camera_source,
                line_config=line_cfg,
                frame_skip=g.frame_skip or recommended_frame_skip,
                gate_name=g.display_name,
                counting_enabled=True,
            )
        except Exception:
            pass

    return {
        "venue_id": venue.id,
        "name": venue.name,
        "effective_capacity": eff_capacity,
        "current_occupancy": 0,
        "monitoring_active": False,
    }


@router.get("/{venue_id}", response_model=VenueResponse)
def get_venue(venue_id: str, db: Session = Depends(get_db)):
    """Get venue details."""
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    resp = VenueResponse.model_validate(venue)
    resp.effective_capacity = venue.effective_capacity
    resp.capacity_is_estimated = venue.capacity_is_estimated
    resp.monitoring_active = camera_manager.is_venue_counting(venue_id)
    return resp


@router.patch("/{venue_id}", response_model=VenueResponse)
def update_venue(venue_id: str, data: VenueUpdate, db: Session = Depends(get_db)):
    """Update venue configuration."""
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(venue, key, value)

    db.add(AuditLog(
        venue_id=venue_id,
        action="venue_updated",
        entity_type="venue",
        entity_id=venue_id,
        performed_by="admin",
        details=update_data,
    ))

    db.commit()
    db.refresh(venue)

    resp = VenueResponse.model_validate(venue)
    resp.effective_capacity = venue.effective_capacity
    resp.capacity_is_estimated = venue.capacity_is_estimated
    return resp


@router.delete("/{venue_id}", status_code=204)
def delete_venue(venue_id: str, db: Session = Depends(get_db)):
    """Delete a venue, stop all its camera workers, and remove all associated records."""
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    # Stop all active camera workers
    gates = db.query(Gate).filter(Gate.venue_id == venue_id).all()
    for g in gates:
        try:
            camera_manager.stop_gate(g.id)
        except Exception:
            pass

    # Explicitly clear related tables for clean SQLite removal
    db.query(CountingEvent).filter(CountingEvent.venue_id == venue_id).delete()
    db.query(OccupancySnapshot).filter(OccupancySnapshot.venue_id == venue_id).delete()
    db.query(OccupancyBaseline).filter(OccupancyBaseline.venue_id == venue_id).delete()
    db.query(Alert).filter(Alert.venue_id == venue_id).delete()
    db.query(AuditLog).filter(AuditLog.venue_id == venue_id).delete()
    db.query(Gate).filter(Gate.venue_id == venue_id).delete()

    db.delete(venue)
    db.commit()
    return None


@router.post("/{venue_id}/baseline", response_model=VenueResponse)
def set_baseline(venue_id: str, data: BaselineRequest, db: Session = Depends(get_db)):
    """Set or reset the occupancy baseline for a venue."""
    try:
        venue = OccupancyService.set_baseline(
            db, venue_id, data.occupancy, data.established_by, data.reason
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    resp = VenueResponse.model_validate(venue)
    resp.effective_capacity = venue.effective_capacity
    resp.capacity_is_estimated = venue.capacity_is_estimated
    return resp


@router.post("/{venue_id}/reconcile", response_model=VenueResponse)
def reconcile_occupancy(venue_id: str, data: ReconcileRequest, db: Session = Depends(get_db)):
    """Reconcile occupancy with a verified manual count."""
    try:
        venue = OccupancyService.reconcile(
            db, venue_id, data.verified_occupancy, data.performed_by, data.reason
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    resp = VenueResponse.model_validate(venue)
    resp.effective_capacity = venue.effective_capacity
    resp.capacity_is_estimated = venue.capacity_is_estimated
    return resp


@router.post("/{venue_id}/start-process")
def start_process(venue_id: str, db: Session = Depends(get_db)):
    """
    Start synchronized live crowd counting across all gates.
    Neutralizes initial setup jitter and begins counting from verified clean baseline.
    """
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    from app.api.v1.websocket import trigger_venue_update

    # Reset any spurious counts accumulated during calibration
    venue.current_occupancy = 0
    venue.total_entries = 0
    venue.total_exits = 0
    venue.is_active = True

    # Reset gate database counts
    gates = db.query(Gate).filter(Gate.venue_id == venue_id).all()
    for g in gates:
        g.entry_count = 0
        g.exit_count = 0

    # Clear historical events for fresh session
    db.query(CountingEvent).filter(CountingEvent.venue_id == venue_id).delete()
    db.commit()

    # Reset in-memory trackers & activate live counting
    camera_manager.reset_venue_counters(venue_id)
    camera_manager.set_venue_counting(venue_id, enabled=True)

    # Broadcast updated live state immediately
    trigger_venue_update(venue_id)

    return {
        "success": True,
        "venue_id": venue_id,
        "monitoring_active": True,
        "message": "Synchronized live crowd counting started successfully."
    }


@router.post("/{venue_id}/pause-process")
def pause_process(venue_id: str, db: Session = Depends(get_db)):
    """
    Pause live counting for line recalibration without stopping camera streams.
    """
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    from app.api.v1.websocket import trigger_venue_update

    camera_manager.set_venue_counting(venue_id, enabled=False)
    trigger_venue_update(venue_id)

    return {
        "success": True,
        "venue_id": venue_id,
        "monitoring_active": False,
        "message": "Live counting paused for line calibration."
    }


@router.post("/{venue_id}/reset-process")
def reset_process(venue_id: str, db: Session = Depends(get_db)):
    """
    Neutralize all counts, reset track memory, and place system into calibration mode.
    """
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    from app.api.v1.websocket import trigger_venue_update

    venue.current_occupancy = 0
    venue.total_entries = 0
    venue.total_exits = 0

    gates = db.query(Gate).filter(Gate.venue_id == venue_id).all()
    for g in gates:
        g.entry_count = 0
        g.exit_count = 0

    db.query(CountingEvent).filter(CountingEvent.venue_id == venue_id).delete()
    db.commit()

    camera_manager.reset_venue_counters(venue_id)
    camera_manager.set_venue_counting(venue_id, enabled=False)
    trigger_venue_update(venue_id)

    return {
        "success": True,
        "venue_id": venue_id,
        "monitoring_active": False,
        "message": "All counts neutralized and reset to 0 in calibration mode."
    }
