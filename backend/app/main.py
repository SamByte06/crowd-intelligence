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
    logger.info("Database initialized, camera manager ready")

    yield

    # Shutdown
    logger.info("Shutting down...")
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
