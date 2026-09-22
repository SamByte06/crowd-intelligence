from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from datetime import datetime

app = FastAPI(
    title="AI Crowd Intelligence API"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# HOME
# ---------------------------------------------------------

@app.get("/api")
def home():
    return {
        "message": "AI Crowd Intelligence Backend is running"
    }


# ---------------------------------------------------------
# EVENT STORAGE
# ---------------------------------------------------------

events_db = []


@app.get("/api/events")
def get_events():
    return {
        "events": events_db,
        "count": len(events_db)
    }


@app.post("/api/events")
def create_event(event: dict):

    event_id = event.get(
        "id",
        f"event_{len(events_db) + 1}"
    )

    event["id"] = event_id
    event["created_at"] = datetime.now().isoformat()

    events_db.append(event)

    return {
        "success": True,
        "message": "Event created successfully",
        "event": event
    }


# ---------------------------------------------------------
# LIVE CROWD STATE
# ---------------------------------------------------------

crowd_state = {
    "timestamp": None,
    "event_id": None,

    "camera_name": None,
    "camera_status": "OFFLINE",

    "total_people": 0,

    "overall_risk": 0,
    "overall_risk_level": "LOW",

    "highest_risk_zone": None,
    "highest_risk_score": 0,
    "highest_risk_level": "LOW",

    "alert": None,

    "zones": []
}


@app.get("/api/current-crowd")
def current_crowd():
    return crowd_state


@app.post("/api/crowd-state")
def update_crowd_state(state: dict):

    global crowd_state

    crowd_state = {
        "timestamp": state.get(
            "timestamp",
            datetime.now().isoformat()
        ),

        "event_id": state.get("event_id"),

        "camera_name": state.get("camera_name"),

        "camera_status": state.get(
            "camera_status",
            "LIVE"
        ),

        "total_people": state.get(
            "total_people",
            0
        ),

        "overall_risk": state.get(
            "overall_risk",
            0
        ),

        "overall_risk_level": state.get(
            "overall_risk_level",
            "LOW"
        ),

        "highest_risk_zone": state.get(
            "highest_risk_zone"
        ),

        "highest_risk_score": state.get(
            "highest_risk_score",
            0
        ),

        "highest_risk_level": state.get(
            "highest_risk_level",
            "LOW"
        ),

        "alert": state.get("alert"),

        "zones": state.get(
            "zones",
            []
        )
    }

    return {
        "success": True,
        "message": "Crowd state updated",
        "timestamp": crowd_state["timestamp"]
    }


# ---------------------------------------------------------
# CAMERA STREAM REGISTRATION
# ---------------------------------------------------------
# The AI laptop sends the CURRENT Cloudflare URL here.
#
# IMPORTANT:
# This endpoint is part of the deployed backend code.
# We deploy it ONCE.
#
# After that, changing Cloudflare URLs only changes DATA.
# It does NOT require another Git push.
# ---------------------------------------------------------

camera_streams = {}


@app.post("/api/camera-stream")
def register_camera_stream(data: dict):

    event_id = data.get("event_id")

    if not event_id:
        return {
            "success": False,
            "message": "event_id is required"
        }

    video_url = data.get("video_url")

    if not video_url:
        return {
            "success": False,
            "message": "video_url is required"
        }

    camera_streams[event_id] = {
        "event_id": event_id,

        "video_url": video_url,

        "camera_name": data.get(
            "camera_name",
            "Camera 01 - Main Entrance"
        ),

        "status": data.get(
            "status",
            "LIVE"
        ),

        "updated_at": datetime.now().isoformat()
    }

    return {
        "success": True,
        "message": "Camera stream registered",
        "stream": camera_streams[event_id]
    }


@app.get("/api/camera-stream")
def get_camera_stream(event_id: Optional[str] = None):

    # If a specific event was requested
    if event_id:

        stream = camera_streams.get(event_id)

        if stream:
            return {
                "success": True,
                "stream": stream
            }

        return {
            "success": False,
            "message": "No camera stream registered for this event",
            "stream": None
        }

    # Return latest available stream
    if camera_streams:

        latest_stream = list(
            camera_streams.values()
        )[-1]

        return {
            "success": True,
            "stream": latest_stream
        }

    return {
        "success": False,
        "message": "No camera stream registered",
        "stream": None
    }


@app.post("/api/camera-stream/offline")
def camera_stream_offline(data: dict):

    event_id = data.get("event_id")

    if not event_id:
        return {
            "success": False,
            "message": "event_id is required"
        }

    if event_id in camera_streams:

        camera_streams[event_id]["status"] = "OFFLINE"

        camera_streams[event_id][
            "updated_at"
        ] = datetime.now().isoformat()

    return {
        "success": True,
        "message": "Camera marked offline"
    }


# ---------------------------------------------------------
# SYSTEM STATUS
# ---------------------------------------------------------

@app.get("/api/system-status")
def system_status():

    live_cameras = sum(
        1
        for stream in camera_streams.values()
        if stream.get("status") == "LIVE"
    )

    return {
        "backend": "CONNECTED",

        "ai_engine": (
            "RUNNING"
            if crowd_state["camera_status"] == "LIVE"
            else "STOPPED"
        ),

        "cameras": live_cameras,

        "active_events": len(events_db),

        "active_alerts": (
            1
            if crowd_state["alert"]
            else 0
        )
    }


# ---------------------------------------------------------
# TEST MODE
# ---------------------------------------------------------

test_mode = {
    "status": "STOPPED",
    "source": None,
    "connected": False
}


@app.get("/api/test-mode/status")
def test_mode_status():
    return test_mode


@app.post("/api/test-mode/start")
def test_mode_start():

    test_mode["status"] = "STARTING"

    return {
        "success": True,
        "message": "Test mode start request received"
    }


@app.post("/api/test-mode/stop")
def test_mode_stop():

    test_mode["status"] = "STOPPED"
    test_mode["connected"] = False

    return {
        "success": True,
        "message": "Test mode stopped"
    }