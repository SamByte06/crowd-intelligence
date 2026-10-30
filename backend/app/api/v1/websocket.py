"""
WebSocket endpoint for real-time dashboard updates.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Set, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.venue import Venue
from app.services.occupancy_service import OccupancyService
from app.services.flow_service import FlowRateService
from app.services.forecast_service import ForecastService
from app.services.alert_service import AlertService
from app.services.camera_manager import camera_manager
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])

# Track active WebSocket connections and their associated venues
active_connections: Set[WebSocket] = set()
connected_venues: dict[WebSocket, str] = {}
main_loop: Optional[asyncio.AbstractEventLoop] = None


@router.websocket("/ws/dashboard/{venue_id}")
async def dashboard_ws(websocket: WebSocket, venue_id: str):
    """WebSocket endpoint for live dashboard and attendee updates."""
    await websocket.accept()
    active_connections.add(websocket)
    connected_venues[websocket] = venue_id
    logger.info(f"WebSocket connected for venue {venue_id}")

    async def send_loop():
        # Send initial state
        state = _get_venue_state(venue_id)
        if state:
            await websocket.send_json({"type": "initial_state", "data": state})

        while True:
            await asyncio.sleep(settings.WS_BROADCAST_INTERVAL)
            cur_state = _get_venue_state(venue_id)
            if cur_state:
                await websocket.send_json({"type": "update", "data": cur_state})

    async def receive_loop():
        while True:
            msg_text = await websocket.receive_text()
            if "ping" in msg_text.lower():
                await websocket.send_text(json.dumps({"type": "pong", "time": time.time()}))

    send_task = asyncio.create_task(send_loop())
    recv_task = asyncio.create_task(receive_loop())

    try:
        done, pending = await asyncio.wait(
            [send_task, recv_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected gracefully for venue {venue_id}")
    except Exception as e:
        logger.debug(f"WebSocket closed: {e}")
    finally:
        send_task.cancel()
        recv_task.cancel()
        active_connections.discard(websocket)
        connected_venues.pop(websocket, None)


def ensure_venue_gates_running(venue_id: str):
    """Ensure camera workers are active for all enabled gates in this venue."""
    from app.models.gate import Gate
    from app.services.gate_counter import LineCrossingConfig

    db = SessionLocal()
    try:
        gates = db.query(Gate).filter(Gate.venue_id == venue_id).all()
        for g in gates:
            if not camera_manager.is_running(g.id):
                source = g.camera_source
                if isinstance(source, str):
                    source = source.strip().strip('"').strip("'")
                    if source.isdigit():
                        source = int(source)
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
                    venue_id=venue_id,
                    camera_source=source,
                    line_config=line_cfg,
                    confidence=g.confidence_threshold or 0.25,
                    frame_skip=g.frame_skip or 2,
                    gate_name=g.display_name,
                    counting_enabled=True,
                )
    except Exception as e:
        logger.warning(f"Could not auto-start camera workers for venue {venue_id}: {e}")
    finally:
        db.close()


@router.websocket("/ws/streams/{venue_id}")
async def video_streams_ws(websocket: WebSocket, venue_id: str):
    """
    High-performance multiplexed video stream WebSocket.
    Streams binary JPEG frames for all gates in a venue over a single TCP connection.
    Eliminates browser 6-connection pool exhaustion when 3+ cameras are monitored.
    """
    await websocket.accept()
    logger.info(f"Video streams multiplexer connected for venue {venue_id}")
    ensure_venue_gates_running(venue_id)
    last_frame_ids: dict[str, int] = {}
    try:
        while True:
            for gate_id, worker in list(camera_manager._workers.items()):
                if worker.venue_id == venue_id:
                    jpeg = worker.get_latest_frame()
                    if jpeg is not None:
                        cur_id = id(jpeg)
                        if last_frame_ids.get(gate_id) != cur_id:
                            last_frame_ids[gate_id] = cur_id
                            # 36-byte ASCII header padded with spaces + JPEG payload
                            header = gate_id.encode("ascii")[:36].ljust(36, b" ")
                            await websocket.send_bytes(header + jpeg)
            await asyncio.sleep(0.033)
    except WebSocketDisconnect:
        logger.info(f"Video streams multiplexer disconnected for venue {venue_id}")
    except Exception as e:
        logger.debug(f"Video streams multiplexer error: {e}")


async def broadcast_venue_state(venue_id: str):
    """Broadcast current venue state immediately to all listening clients."""
    state = _get_venue_state(venue_id)
    if not state:
        return
    message = json.dumps({"type": "update", "data": state})
    targets = [ws for ws, vid in list(connected_venues.items()) if vid == venue_id]
    for ws in targets:
        try:
            await ws.send_text(message)
        except Exception:
            active_connections.discard(ws)
            connected_venues.pop(ws, None)


def trigger_venue_update(venue_id: str):
    """Thread-safe trigger invoked by camera workers on crossing events."""
    global main_loop
    if main_loop and main_loop.is_running():
        try:
            asyncio.run_coroutine_threadsafe(broadcast_venue_state(venue_id), main_loop)
        except Exception as e:
            logger.error(f"Failed to schedule websocket broadcast: {e}")


def _get_venue_state(venue_id: str) -> dict | None:
    """Gather all venue state for dashboard."""
    db = SessionLocal()
    try:
        venue = db.query(Venue).filter(Venue.id == venue_id).first()
        if not venue:
            return None

        occupancy = OccupancyService.get_occupancy(db, venue_id)
        flow = FlowRateService.calculate(db, venue_id)
        forecast_data = ForecastService.forecast(db, venue_id)
        active_alerts = AlertService.get_active_alerts(db, venue_id)

        # Evaluate alerts (side effect: creates new alerts if conditions met)
        AlertService.evaluate(db, venue_id)

        # Save snapshot
        OccupancyService.save_snapshot(
            db, venue_id,
            entry_rate=flow["entry_rate_per_min"],
            exit_rate=flow["exit_rate_per_min"],
            net_inflow=flow["net_inflow_per_min"],
        )

        ensure_venue_gates_running(venue_id)
        from app.models.gate import Gate
        gates = db.query(Gate).filter(Gate.venue_id == venue_id).all()
        gate_data = [
            {
                "id": g.id,
                "display_name": g.display_name,
                "gate_type": g.gate_type.value if hasattr(g.gate_type, "value") else str(g.gate_type),
                "status": g.status.value if hasattr(g.status, "value") else str(g.status),
                "entry_count": g.entry_count or 0,
                "exit_count": g.exit_count or 0,
                "last_frame_at": g.last_frame_at.isoformat() if g.last_frame_at else None,
                "last_count_at": g.last_count_at.isoformat() if g.last_count_at else None,
                "error_message": g.error_message,
                "line_start_x": g.line_start_x,
                "line_start_y": g.line_start_y,
                "line_end_x": g.line_end_x,
                "line_end_y": g.line_end_y,
                "counting_direction": g.counting_direction or "any",
            }
            for g in gates
        ]

        venue_dict = {
            "id": venue.id,
            "name": venue.name,
            "description": venue.description,
            "location": venue.location,
            "usable_area_sqm": venue.usable_area_sqm,
            "max_capacity": venue.max_capacity,
            "effective_capacity": venue.effective_capacity,
            "capacity_is_estimated": venue.capacity_is_estimated,
            "current_occupancy": occupancy["current_occupancy"],
            "total_entries": occupancy["total_entries"],
            "total_exits": occupancy["total_exits"],
            "baseline_established": venue.baseline_established,
            "monitoring_active": camera_manager.is_venue_counting(venue_id),
        }

        camera_health = camera_manager.get_health()

        # Convert datetimes for JSON
        def serialize(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            return obj

        return {
            "venue": venue_dict,
            "monitoring_active": camera_manager.is_venue_counting(venue_id),
            "occupancy": {
                **occupancy,
                "last_updated": occupancy["last_updated"].isoformat() if occupancy.get("last_updated") else None,
            },
            "flow": {
                **flow,
                "measured_at": flow["measured_at"].isoformat() if flow.get("measured_at") else None,
            },
            "forecast": {
                **forecast_data,
                "measured_at": forecast_data["measured_at"].isoformat() if forecast_data.get("measured_at") else None,
            },
            "alerts": [
                {
                    "id": a.id,
                    "severity": a.severity.value,
                    "status": a.status.value,
                    "title": a.title,
                    "message": a.message,
                    "recommended_action": a.recommended_action,
                    "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
                }
                for a in active_alerts
            ],
            "gates": gate_data,
            "camera_health": camera_health,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting venue state: {e}")
        return None
    finally:
        db.close()


async def broadcast_event(venue_id: str, event_type: str, data: dict):
    """Broadcast an event to all connected clients for a venue."""
    message = json.dumps({"type": event_type, "data": data})
    disconnected = set()
    for ws in active_connections:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.add(ws)
    active_connections -= disconnected
