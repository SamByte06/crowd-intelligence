from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import json
import os

app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# crowd_state.json is created by track_webcam.py in the main project folder.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(PROJECT_ROOT, "crowd_state.json")


@app.get("/")
def home():
    return {
        "message": "AI Crowd Intelligence Backend is running"
    }


@app.get("/api/current-crowd")
def current_crowd():
    if not os.path.exists(STATE_FILE):
        return JSONResponse(
            status_code=503,
            content={
                "status": "waiting",
                "message": "Waiting for track_webcam.py to provide live crowd data"
            }
        )

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            state = json.load(file)

        return state

    except (OSError, json.JSONDecodeError):
        return JSONResponse(
            status_code=503,
            content={
                "status": "waiting",
                "message": "Live crowd state is temporarily unavailable"
            }
        )
