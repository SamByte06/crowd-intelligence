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
# SYSTEM STATUS
# ---------------------------------------------------------

@app.get("/api/system-status")
def system_status():

    return {
        "backend": "CONNECTED",

        "ai_engine": (
            "RUNNING"
            if crowd_state["camera_status"] == "LIVE"
            else "STOPPED"
        ),

        "cameras": (
            1
            if crowd_state["camera_status"] == "LIVE"
            else 0
        ),

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