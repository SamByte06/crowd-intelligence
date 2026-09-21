from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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




@app.get("/api")
def home():
    return {
        "message": "AI Crowd Intelligence Backend is running"
    }


@app.get("/api/current-crowd")
def current_crowd():
    return {
        "people": 0,
        "risk": 0,
        "risk_level": "SAFE",
        "trend": "STABLE"
    }