"""
Application configuration loaded from environment variables with sensible defaults.
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "AI Crowd Intelligence System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # Database — explicitly pinned to backend directory to prevent split-database issues
    DATABASE_URL: str = Field(
        default=f"sqlite:///{(Path(__file__).resolve().parent.parent / 'crowd_intelligence.db').as_posix()}",
        description="SQLAlchemy database URL"
    )

    # YOLO Detection — pinned to backend directory to prevent relative path lookup failures
    YOLO_MODEL_PATH: str = Field(
        default=str(Path(__file__).resolve().parent.parent / "yolo11s.pt"),
        description="Path to YOLO model weights file"
    )
    HEAD_MODEL_PATH: str = Field(
        default=str(Path(__file__).resolve().parent.parent / "11s-head.pt"),
        description="Path to dedicated head detection weights file"
    )
    USE_HEAD_TRACKING: bool = Field(
        default=True,
        description="Enable dedicated head-based detection and persistent tracking"
    )
    YOLO_CONFIDENCE: float = 0.25
    YOLO_IOU_THRESHOLD: float = 0.45
    YOLO_IMAGE_SIZE: int = 320
    YOLO_DEVICE: str = "auto"  # "auto", "cpu", "cuda", "0"

    # Tracker
    TRACKER_TYPE: str = "bytetrack.yaml"  # Fast, accurate, zero optical flow latency

    # Camera Processing
    CAMERA_FRAME_QUEUE_SIZE: int = 4
    CAMERA_RECONNECT_MAX_ATTEMPTS: int = 10
    CAMERA_RECONNECT_BASE_DELAY: float = 2.0
    CAMERA_RECONNECT_MAX_DELAY: float = 60.0
    CAMERA_HEALTH_CHECK_INTERVAL: float = 30.0
    CAMERA_FRAME_TIMEOUT: float = 10.0

    # Occupancy
    DEFAULT_DENSITY_PER_SQM: float = 2.0
    MAX_OCCUPANCY_HARD_LIMIT: int = 100000

    # Flow Rates
    FLOW_WINDOW_SECONDS: int = 60
    FLOW_SMOOTHING_FACTOR: float = 0.3

    # Forecasting
    FORECAST_HORIZONS_MINUTES: str = "5,10,15,30"
    FORECAST_MIN_DATA_POINTS: int = 3

    # Alerts
    ALERT_COOLDOWN_SECONDS: int = 300
    ALERT_CONFIRMATION_SECONDS: int = 30
    DEFAULT_WARNING_THRESHOLD: float = 0.75
    DEFAULT_CRITICAL_THRESHOLD: float = 0.90

    # Security
    SECRET_KEY: str = "change-me-in-production-use-strong-random-key"
    API_KEY: str = ""  # Empty = no auth in dev mode

    # WebSocket
    WS_BROADCAST_INTERVAL: float = 2.0

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def forecast_horizons_list(self) -> list[int]:
        return [int(h.strip()) for h in self.FORECAST_HORIZONS_MINUTES.split(",")]

    @property
    def resolved_yolo_device(self) -> str:
        if self.YOLO_DEVICE == "auto":
            try:
                import torch
                return "0" if torch.cuda.is_available() else "cpu"
            except ImportError:
                return "cpu"
        return self.YOLO_DEVICE

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()
