"""
FastAPI application entry point.
"""

import os
import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db, SessionLocal, get_db
from app.api.v1 import venues, gates, monitoring, websocket
from app.services.camera_manager import camera_manager
from app.services.occupancy_service import OccupancyService
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import Depends

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Track startup time
_start_time = time.time()


def _setup_crossing_handler():
    """Register callback to persist crossing events from camera workers."""

    def handle_crossing(venue_id: str, gate_id: str, event):
        """Called by camera workers when a line crossing is detected."""
        if getattr(event, "is_blocked", False):
            logger.warning(
                f"Access Denied (Anti-Passback): venue={venue_id} gate={gate_id} track={event.track_id} "
                f"reason={getattr(event, 'block_reason', 'Already passed')}"
            )
            return

        db = SessionLocal()
        try:
            OccupancyService.record_crossing(
                db=db,
                venue_id=venue_id,
                gate_id=gate_id,
                direction=event.direction,
                track_id=event.track_id,
                confidence=event.confidence,
            )
            # Push instant real-time update over WebSocket
            try:
                from app.api.v1.websocket import trigger_venue_update
                trigger_venue_update(venue_id)
            except Exception:
                pass

            # Evaluate threshold escalation and broadcast native Web Push to background devices
            try:
                from app.services.alert_service import AlertService
                new_alerts = AlertService.evaluate(db, venue_id)
                if new_alerts:
                    from app.services.push_service import broadcast_web_push
                    from app.models.venue import Venue
                    venue = db.query(Venue).filter(Venue.id == venue_id).first()
                    v_name = venue.name if venue else "Monitored Event"
                    for a in new_alerts:
                        sev = a.severity.value if hasattr(a.severity, "value") else str(a.severity)
                        broadcast_web_push(
                            venue_id=venue_id,
                            title=f"{'🚨 CRITICAL ALERT' if sev == 'CRITICAL' else '⚠️ RUSH WARNING'} • {v_name}",
                            body=a.message,
                            severity=sev,
                            tag=f"crowd-alert-{sev.lower()}",
                        )
            except Exception as e_push:
                logger.debug(f"Push evaluation error: {e_push}")
        except Exception as e:
            logger.error(f"Failed to record crossing: {e}")
        finally:
            db.close()

    camera_manager.on_crossing(handle_crossing)

    def handle_status_change(gate_id: str, status: str, error: str | None):
        """Called by camera workers when status changes."""
        db = SessionLocal()
        try:
            from app.models.gate import Gate
            gate = db.query(Gate).filter(Gate.id == gate_id).first()
            if gate:
                gate.status = status
                gate.error_message = error
                db.commit()
        except Exception as e:
            logger.error(f"Failed to update gate status: {e}")
        finally:
            db.close()

    camera_manager.on_status_change(handle_status_change)


def _start_all_active_venues():
    """
    Ensure all active venues and their configured gates are running in CameraManager on server boot.
    Completely decouples CCTV capture, YOLO detection, ByteTrack tracking, and gate counting
    from whether any frontend browser tab is open or connected.
    """
    db = SessionLocal()
    try:
        from app.models.venue import Venue
        from app.models.gate import Gate
        from app.services.gate_counter import LineCrossingConfig

        venues = db.query(Venue).filter(Venue.is_active == True).all()
        logger.info(f"Auto-starting camera processing workers for {len(venues)} active venues...")
        for v in venues:
            gates = db.query(Gate).filter(Gate.venue_id == v.id).all()
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
                        venue_id=v.id,
                        camera_source=source,
                        line_config=line_cfg,
                        confidence=g.confidence_threshold or 0.25,
                        frame_skip=g.frame_skip or 2,
                        gate_name=g.display_name,
                        counting_enabled=True,
                    )
    except Exception as e:
        logger.error(f"Error starting active venues on startup: {e}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup and shutdown."""
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    try:
        import app.api.v1.websocket as ws_module
        ws_module.main_loop = asyncio.get_running_loop()
    except Exception:
        pass

    if os.environ.get("TESTING") != "1":
        init_db()
    _setup_crossing_handler()
    # Fully decouple monitoring from frontend: auto-start all cameras on server startup
    _start_all_active_venues()
    logger.info("Database initialized, all camera workers and AI tracking active on backend")

    # Periodic background alert evaluator and server-side Web Push dispatcher
    # Dispatches alerts & silent timeline straight into subscriber devices via Google FCM even if browser is closed / in Instagram
    async def alert_background_worker():
        last_timeline_time = {}
        last_percent_seen = {}
        last_alert_level = {}
        last_alert_time = {}
        severity_weights = {"NORMAL": 0, "MODERATE": 1, "HIGH": 2, "CRITICAL": 3}

        while True:
            try:
                await asyncio.sleep(4)
                db = SessionLocal()
                try:
                    from app.models.venue import Venue
                    from app.services.push_service import broadcast_web_push
                    from app.services.forecast_service import ForecastService

                    venues = db.query(Venue).filter(Venue.is_active == True).all()
                    now = time.time()

                    for v in venues:
                        cap = v.effective_capacity or 1000
                        count = v.current_occupancy or 0
                        pct = round((count / cap) * 100, 1) if cap > 0 else 0

                        # Check if admin stopped the notification campaign
                        campaign_active = getattr(v, "notification_campaign_active", True)
                        reminder_interval = getattr(v, "reminder_interval_seconds", 60) or 60

                        # 1. Evaluate alert severity level: NORMAL, MODERATE, HIGH, CRITICAL
                        crit_thresh = (v.critical_threshold * 100) if v.critical_threshold else 90.0
                        high_thresh = (v.warning_threshold * 100) if v.warning_threshold else 75.0
                        mod_thresh = (v.moderate_threshold * 100) if getattr(v, "moderate_threshold", None) else 60.0

                        if pct >= crit_thresh:
                            level = "CRITICAL"
                        elif pct >= high_thresh:
                            level = "HIGH"
                        elif pct >= mod_thresh:
                            level = "MODERATE"
                        else:
                            level = "NORMAL"

                        prev_level = last_alert_level.get(v.id, "NORMAL")
                        prev_alert_t = last_alert_time.get(v.id, 0)

                        is_escalation = severity_weights.get(level, 0) > severity_weights.get(prev_level, 0)
                        is_reminder = (level == prev_level and level != "NORMAL" and (now - prev_alert_t >= reminder_interval))

                        if campaign_active and level != "NORMAL" and (is_escalation or is_reminder):
                            last_alert_level[v.id] = level
                            last_alert_time[v.id] = now

                            if level == "CRITICAL":
                                title = f"🚨 CRITICAL CROWD ALARM • {v.name}"
                                body = f"Critical threshold reached! {pct}% capacity ({count}/{cap}). Urgent gate holds and flow restrictions in effect."
                            elif level == "HIGH":
                                title = f"⚠️ HIGH RUSH WARNING • {v.name}"
                                body = f"Venue has reached {pct}% capacity ({count}/{cap}). Substantial queues forming at gates."
                            else:
                                title = f"🟡 MODERATE RUSH ALERT • {v.name}"
                                body = f"Crowd density rising: {pct}% full ({count}/{cap}). Moderate influx detected."

                            broadcast_web_push(
                                venue_id=v.id,
                                title=title,
                                body=body,
                                severity=level,
                                tag=f"crowd-alert-{level.lower()}",
                            )

                        elif level == "NORMAL" and prev_level != "NORMAL":
                            # Crowd returned to NORMAL: stop recurring reminders and send resolution notification
                            last_alert_level[v.id] = "NORMAL"
                            if campaign_active:
                                broadcast_web_push(
                                    venue_id=v.id,
                                    title=f"🟢 CROWD NORMALIZED • {v.name}",
                                    body=f"Crowd conditions have normalized to {pct}% ({count}/{cap}). Safe flow restored at all gates.",
                                    severity="NORMAL",
                                    tag="crowd-alert-resolved",
                                )

                        # 2. Silent Live Timeline Push (Flipkart / Zomato style) every 15s or on >= 1% change
                        prev_time = last_timeline_time.get(v.id, 0)
                        prev_pct = last_percent_seen.get(v.id, -1)
                        if (now - prev_time >= 15) or (abs(pct - prev_pct) >= 1.0):
                            last_timeline_time[v.id] = now
                            last_percent_seen[v.id] = pct

                            try:
                                fc = ForecastService.forecast(db, v.id)
                                time_to_cap = fc.get("time_to_critical_minutes")
                                inflow = fc.get("net_inflow_rate", 0)
                            except Exception:
                                time_to_cap = None
                                inflow = 0

                            status_emoji = "🔴" if pct >= 90 else ("🟡" if pct >= 75 else ("🟠" if pct >= 60 else "🟢"))
                            status_word = "CRITICAL CAPACITY" if pct >= 90 else ("HIGH RUSH" if pct >= 75 else ("MODERATE RUSH" if pct >= 60 else "SAFE FLOW"))
                            time_text = f"Full in ~{round(time_to_cap)}m" if (time_to_cap and time_to_cap > 0) else ("Area FULL" if pct >= 100 else "Steady Flow")
                            flow_text = f"+{inflow:.0f}/m" if inflow > 0 else f"{inflow:.0f}/m"

                            title = f"{status_emoji} {status_word}: {v.name}"
                            body = f"⏱️ {time_text}  |  👥 {pct}% ({count}/{cap})\n⚡ Speed: {flow_text}  |  [Safe 🟢 ──> Rush 🟡 ──> Full 🔴]"

                            broadcast_web_push(
                                venue_id=v.id,
                                title=title,
                                body=body,
                                severity="NORMAL",
                                tag="live-crowd-timeline",
                            )
                except Exception as e_loop:
                    logger.debug(f"Alert loop debug: {e_loop}")
                finally:
                    db.close()
            except asyncio.CancelledError:
                break
            except Exception:
                pass
            except Exception:
                pass

    alert_task = asyncio.create_task(alert_background_worker())

    yield

    # Shutdown
    logger.info("Shutting down...")
    alert_task.cancel()
    camera_manager.stop_all()
    logger.info("All camera workers stopped")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-Powered Crowd Intelligence & Entry-Exit Management System",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API v1 routes
app.include_router(venues.router, prefix="/api/v1")
app.include_router(gates.router, prefix="/api/v1")
app.include_router(monitoring.router, prefix="/api/v1")
app.include_router(websocket.router, prefix="/api/v1")


@app.get("/health")
@app.get("/api/v1/health")
def health_check(db: Session = Depends(get_db)):
    """Application health check."""
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "database": db_status,
        "cameras_active": camera_manager.active_count,
        "uptime_seconds": round(time.time() - _start_time, 1),
    }


# Mount and serve built frontend static files if present (for single-container/HuggingFace deployment)
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

static_dir = Path(__file__).resolve().parent.parent / "static"
if static_dir.exists() and (static_dir / "index.html").exists():
    if (static_dir / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api") or full_path.startswith("ws") or full_path == "health":
            return None
        target_file = static_dir / full_path
        if target_file.is_file():
            return FileResponse(str(target_file))
        return FileResponse(str(static_dir / "index.html"))
else:
    @app.get("/")
    def root():
        """Root endpoint."""
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs": "/docs",
            "health": "/api/v1/health",
        }
