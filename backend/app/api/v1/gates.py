"""
Gate API endpoints — Gate CRUD, camera control, and connection testing.
"""

import os
import uuid
import shutil
import time
import asyncio
from typing import Optional
from datetime import datetime
import cv2
import numpy as np

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models.gate import Gate, GateType, CameraSourceType, GateStatus
from app.models.venue import Venue
from app.models.audit_log import AuditLog
from app.schemas.gate import GateCreate, GateUpdate, GateResponse
from app.services.camera_manager import camera_manager
from app.services.gate_counter import LineCrossingConfig

router = APIRouter(tags=["Gates"])


@router.get("/venues/{venue_id}/gates", response_model=list[GateResponse])
def list_gates(venue_id: str, db: Session = Depends(get_db)):
    """List all gates for a venue."""
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    gates = db.query(Gate).filter(Gate.venue_id == venue_id).all()
    return [GateResponse.model_validate(g) for g in gates]


@router.post("/venues/{venue_id}/gates", response_model=GateResponse, status_code=201)
def create_gate(venue_id: str, data: GateCreate, db: Session = Depends(get_db)):
    """Add a new gate to a venue."""
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    gate = Gate(
        venue_id=venue_id,
        display_name=data.display_name,
        gate_type=GateType(data.gate_type),
        camera_source_type=CameraSourceType(data.camera_source_type),
        camera_source=data.camera_source,
        camera_username=data.camera_username,
        camera_password=data.camera_password,
        line_start_x=data.line_start_x,
        line_start_y=data.line_start_y,
        line_end_x=data.line_end_x,
        line_end_y=data.line_end_y,
        counting_direction=data.counting_direction,
        confidence_threshold=data.confidence_threshold,
        frame_skip=data.frame_skip,
        is_enabled=data.is_enabled,
    )
    db.add(gate)

    db.add(AuditLog(
        venue_id=venue_id,
        action="gate_created",
        entity_type="gate",
        entity_id=gate.id,
        performed_by="admin",
        details={"display_name": data.display_name, "gate_type": data.gate_type},
    ))

    db.commit()
    db.refresh(gate)
    return GateResponse.model_validate(gate)


@router.patch("/gates/{gate_id}", response_model=GateResponse)
def update_gate(gate_id: str, data: GateUpdate, db: Session = Depends(get_db)):
    """Update gate configuration."""
    gate = db.query(Gate).filter(Gate.id == gate_id).first()
    if not gate:
        raise HTTPException(status_code=404, detail="Gate not found")

    # Stop worker if running before changing config
    if camera_manager.is_running(gate_id):
        camera_manager.stop_gate(gate_id)

    update_data = data.model_dump(exclude_unset=True)
    if "gate_type" in update_data:
        update_data["gate_type"] = GateType(update_data["gate_type"])
    if "camera_source_type" in update_data:
        update_data["camera_source_type"] = CameraSourceType(update_data["camera_source_type"])

    for key, value in update_data.items():
        setattr(gate, key, value)

    db.add(AuditLog(
        venue_id=gate.venue_id,
        action="gate_updated",
        entity_type="gate",
        entity_id=gate_id,
        performed_by="admin",
        details={k: str(v) for k, v in update_data.items() if k not in ("camera_password",)},
    ))

    db.commit()
    db.refresh(gate)
    return GateResponse.model_validate(gate)


@router.delete("/gates/{gate_id}", status_code=204)
def delete_gate(gate_id: str, db: Session = Depends(get_db)):
    """Delete a gate."""
    gate = db.query(Gate).filter(Gate.id == gate_id).first()
    if not gate:
        raise HTTPException(status_code=404, detail="Gate not found")

    # Stop worker if running
    if camera_manager.is_running(gate_id):
        camera_manager.stop_gate(gate_id)

    db.add(AuditLog(
        venue_id=gate.venue_id,
        action="gate_deleted",
        entity_type="gate",
        entity_id=gate_id,
        performed_by="admin",
        details={"display_name": gate.display_name},
    ))

    db.delete(gate)
    db.commit()


@router.post("/gates/upload-video")
async def upload_gate_video(file: UploadFile = File(...)):
    """
    Upload a local video file (.mp4, .avi, .mov, .mkv) for use as a gate camera source.
    Saves to media_uploads directory using efficient async chunks and returns the absolute local path.
    """
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No video file provided")

    ext = os.path.splitext(file.filename)[1].lower()
    allowed = [".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"]
    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{ext}'. Allowed video formats: {', '.join(allowed)}"
        )

    upload_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "media_uploads"))
    os.makedirs(upload_dir, exist_ok=True)

    clean_basename = os.path.basename(file.filename).replace(" ", "_")
    safe_name = f"{uuid.uuid4().hex[:8]}_{clean_basename}"
    dest_path = os.path.join(upload_dir, safe_name)

    try:
        with open(dest_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                f.write(chunk)
    except Exception as e:
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Failed to save video file: {str(e)}")
    finally:
        await file.close()

    return {
        "success": True,
        "filename": file.filename,
        "file_path": dest_path,
        "size_bytes": os.path.getsize(dest_path),
    }


@router.post("/gates/{gate_id}/test-connection")
def test_connection(gate_id: str, db: Session = Depends(get_db)):
    """Test a gate's camera connection."""
    gate = db.query(Gate).filter(Gate.id == gate_id).first()
    if not gate:
        raise HTTPException(status_code=404, detail="Gate not found")

    import cv2
    source = gate.camera_source
    if isinstance(source, str):
        source = source.strip().strip('"').strip("'")

    if isinstance(source, str) and source.isdigit():
        source = int(source)
    elif isinstance(source, str) and ("youtube.com" in source or "youtu.be" in source):
        from app.services.camera_manager import resolve_youtube_source
        source = resolve_youtube_source(source)
    elif isinstance(source, str) and not source.startswith(("rtsp://", "rtmp://", "http://", "https://")):
        if not os.path.exists(source) and not os.path.exists(os.path.abspath(source)):
            return {"success": False, "message": f"Local video file not found: {source}"}
        source = os.path.abspath(source)

    try:
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            return {"success": False, "message": f"Cannot open camera source: {gate.camera_source}"}

        ret, frame = cap.read()
        cap.release()

        if ret:
            h, w = frame.shape[:2]
            return {
                "success": True,
                "message": "Camera connected successfully",
                "resolution": f"{w}x{h}",
            }
        else:
            return {"success": False, "message": "Connected but could not read frame"}

    except Exception as e:
        return {"success": False, "message": f"Connection error: {str(e)}"}


@router.post("/gates/{gate_id}/start")
def start_gate(gate_id: str, db: Session = Depends(get_db)):
    """Start camera processing for a gate."""
    gate = db.query(Gate).filter(Gate.id == gate_id).first()
    if not gate:
        raise HTTPException(status_code=404, detail="Gate not found")

    if not gate.is_enabled:
        raise HTTPException(status_code=400, detail="Gate is disabled")

    venue = db.query(Venue).filter(Venue.id == gate.venue_id).first()
    if not venue or not venue.baseline_established:
        raise HTTPException(
            status_code=400,
            detail="Occupancy baseline must be established before starting cameras"
        )

    if camera_manager.is_running(gate_id):
        return {"message": "Camera already running", "gate_id": gate_id}

    line_config = LineCrossingConfig(
        start_x=gate.line_start_x,
        start_y=gate.line_start_y,
        end_x=gate.line_end_x,
        end_y=gate.line_end_y,
        counting_direction=gate.counting_direction or "any",
        gate_type=gate.gate_type.value if hasattr(gate.gate_type, "value") else str(gate.gate_type),
        single_pass_only=True,
    )

    source = gate.camera_source
    success = camera_manager.start_gate(
        gate_id=gate.id,
        venue_id=gate.venue_id,
        camera_source=source,
        line_config=line_config,
        confidence=gate.confidence_threshold,
        frame_skip=gate.frame_skip,
        gate_name=gate.display_name,
        counting_enabled=True,
    )

    if success:
        gate.status = GateStatus.CONNECTING
        db.commit()
        return {"message": "Camera started", "gate_id": gate_id}
    else:
        raise HTTPException(status_code=500, detail="Failed to start camera worker")


@router.post("/gates/{gate_id}/stop")
def stop_gate(gate_id: str, db: Session = Depends(get_db)):
    """Stop camera processing for a gate."""
    gate = db.query(Gate).filter(Gate.id == gate_id).first()
    if not gate:
        raise HTTPException(status_code=404, detail="Gate not found")

    camera_manager.stop_gate(gate_id)
    gate.status = GateStatus.INACTIVE
    db.commit()
    return {"message": "Camera stopped", "gate_id": gate_id}


@router.get("/gates/{gate_id}/stream")
async def get_gate_stream(gate_id: str):
    """
    Live MJPEG video stream for a gate camera.
    Uses async non-blocking streaming without holding database connections open.
    """
    db = SessionLocal()
    try:
        gate = db.query(Gate).filter(Gate.id == gate_id).first()
        if not gate:
            raise HTTPException(status_code=404, detail="Gate not found")
        gate_name = str(gate.display_name or f"Gate {gate_id[:8]}")
        camera_source = str(gate.camera_source or "")
        gate_status_val = gate.status.value if hasattr(gate.status, "value") else str(gate.status)
        lx1, ly1 = int((gate.line_start_x or 0.0) * 640), int((gate.line_start_y or 0.5) * 360)
        lx2, ly2 = int((gate.line_end_x or 1.0) * 640), int((gate.line_end_y or 0.5) * 360)
    finally:
        db.close()  # IMMEDIATELY RELEASE DATABASE CONNECTION

    # Pre-encode standby frame so new stream connections immediately receive bytes
    standby_frame = np.full((360, 640, 3), (24, 32, 47), dtype=np.uint8)
    cv2.line(standby_frame, (lx1, ly1), (lx2, ly2), (60, 70, 90), 1)
    cv2.putText(standby_frame, gate_name.upper(), (40, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (240, 245, 255), 2, cv2.LINE_AA)
    cv2.putText(standby_frame, f"SOURCE: {camera_source[:45]}", (40, 185), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (140, 155, 175), 1, cv2.LINE_AA)
    cv2.putText(standby_frame, f"STATUS: {gate_status_val} - CONNECTING STREAM...", (40, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (90, 170, 240), 1, cv2.LINE_AA)
    ret, buf = cv2.imencode(".jpg", standby_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
    standby_bytes = buf.tobytes() if ret else b""

    async def frame_generator():
        while True:
            real_frame = camera_manager.get_latest_frame(gate_id)
            if real_frame is not None:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + real_frame + b"\r\n")
                await asyncio.sleep(0.04)
            else:
                if standby_bytes:
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + standby_bytes + b"\r\n")
                await asyncio.sleep(0.25)

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "keep-alive",
        },
    )


class LineConfigUpdate(BaseModel):
    start_x: Optional[float] = None
    start_y: Optional[float] = None
    end_x: Optional[float] = None
    end_y: Optional[float] = None
    counting_direction: Optional[str] = None
    reset_anti_passback: Optional[bool] = False


@router.patch("/gates/{gate_id}/line-config")
def update_gate_line_config(gate_id: str, data: LineConfigUpdate, db: Session = Depends(get_db)):
    """Update counting line coordinates or direction for a gate in real time."""
    gate = db.query(Gate).filter(Gate.id == gate_id).first()
    if not gate:
        raise HTTPException(status_code=404, detail="Gate not found")

    if data.start_x is not None:
        gate.line_start_x = max(0.0, min(1.0, data.start_x))
    if data.start_y is not None:
        gate.line_start_y = max(0.0, min(1.0, data.start_y))
    if data.end_x is not None:
        gate.line_end_x = max(0.0, min(1.0, data.end_x))
    if data.end_y is not None:
        gate.line_end_y = max(0.0, min(1.0, data.end_y))
    if data.counting_direction is not None:
        gate.counting_direction = data.counting_direction

    # Immediately push to active camera worker thread in-memory (< 1ms, before DB I/O)
    camera_manager.update_gate_line(
        gate_id=gate.id,
        start_x=gate.line_start_x,
        start_y=gate.line_start_y,
        end_x=gate.line_end_x,
        end_y=gate.line_end_y,
        counting_direction=gate.counting_direction,
    )

    if data.reset_anti_passback:
        worker = camera_manager._workers.get(gate.id)
        if worker:
            worker.gate_counter.registered_entered.clear()
            worker.gate_counter.registered_exited.clear()
            worker.gate_counter.blocked_violations.clear()

    db.commit()
    db.refresh(gate)

    return {
        "success": True,
        "gate_id": gate.id,
        "line_start_x": gate.line_start_x,
        "line_start_y": gate.line_start_y,
        "line_end_x": gate.line_end_x,
        "line_end_y": gate.line_end_y,
        "counting_direction": gate.counting_direction,
    }


