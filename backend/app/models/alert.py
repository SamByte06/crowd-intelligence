"""Alert database model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey, Enum as SQLEnum, Text
from sqlalchemy.orm import relationship

from app.database import Base

import enum


class AlertSeverity(str, enum.Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    DATA_UNRELIABLE = "DATA_UNRELIABLE"


class AlertStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    venue_id = Column(String(36), ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)

    severity = Column(SQLEnum(AlertSeverity), nullable=False)
    status = Column(SQLEnum(AlertStatus), default=AlertStatus.ACTIVE)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    recommended_action = Column(Text, nullable=True)

    # Context at time of alert
    occupancy_at_trigger = Column(Integer, nullable=True)
    capacity_at_trigger = Column(Integer, nullable=True)
    entry_rate_at_trigger = Column(Float, nullable=True)
    exit_rate_at_trigger = Column(Float, nullable=True)
    forecast_occupancy = Column(Integer, nullable=True)
    trigger_reason = Column(String(255), nullable=True)

    # Lifecycle
    triggered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(String(255), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(255), nullable=True)
    resolution_note = Column(Text, nullable=True)

    # Deduplication
    alert_type_key = Column(String(255), nullable=True, index=True)
    cooldown_until = Column(DateTime, nullable=True)

    # Relationship
    venue = relationship("Venue", back_populates="alerts")
