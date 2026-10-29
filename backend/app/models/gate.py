"""Gate (entry/exit point) database model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey, Enum as SQLEnum, JSON
from sqlalchemy.orm import relationship

from app.database import Base

import enum


class GateType(str, enum.Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


class GateStatus(str, enum.Enum):
    INACTIVE = "INACTIVE"
    CONNECTING = "CONNECTING"
    ACTIVE = "ACTIVE"
    ERROR = "ERROR"
    DISCONNECTED = "DISCONNECTED"


class CameraSourceType(str, enum.Enum):
    WEBCAM = "WEBCAM"
    VIDEO_FILE = "VIDEO_FILE"
    RTSP = "RTSP"
    HTTP = "HTTP"


class Gate(Base):
    __tablename__ = "gates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    venue_id = Column(String(36), ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)
    display_name = Column(String(255), nullable=False)
    gate_type = Column(SQLEnum(GateType), nullable=False)

    # Camera configuration
    camera_source_type = Column(SQLEnum(CameraSourceType), default=CameraSourceType.WEBCAM)
    camera_source = Column(String(1024), default="0")  # URL, file path, or device index
    camera_username = Column(String(255), nullable=True)  # stored, never exposed in API
    camera_password = Column(String(255), nullable=True)  # stored, never exposed in API

    # Counting line configuration (normalized coordinates 0.0-1.0)
    line_start_x = Column(Float, default=0.0)
    line_start_y = Column(Float, default=0.5)
    line_end_x = Column(Float, default=1.0)
    line_end_y = Column(Float, default=0.5)
    counting_direction = Column(String(10), default="down")  # "up", "down", "left", "right"

    # Detection settings
    confidence_threshold = Column(Float, default=0.25)
    frame_skip = Column(Integer, default=1)  # Process every Nth frame

    # State
    is_enabled = Column(Boolean, default=True)
    status = Column(SQLEnum(GateStatus), default=GateStatus.INACTIVE)
    last_frame_at = Column(DateTime, nullable=True)
    last_count_at = Column(DateTime, nullable=True)
    error_message = Column(String(1024), nullable=True)
    reconnect_attempts = Column(Integer, default=0)

    # Counts
    entry_count = Column(Integer, default=0)
    exit_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    venue = relationship("Venue", back_populates="gates")
    counting_events = relationship("CountingEvent", back_populates="gate", cascade="all, delete-orphan")
