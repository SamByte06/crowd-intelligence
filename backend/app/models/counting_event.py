"""Counting event database model — the immutable event ledger."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship

from app.database import Base

import enum


class CrossingDirection(str, enum.Enum):
    IN = "IN"
    OUT = "OUT"


class CountingEvent(Base):
    __tablename__ = "counting_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    venue_id = Column(String(36), ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)
    gate_id = Column(String(36), ForeignKey("gates.id", ondelete="CASCADE"), nullable=False)

    direction = Column(SQLEnum(CrossingDirection), nullable=False)
    track_id = Column(Integer, nullable=True)  # Scoped to camera/session
    confidence = Column(Float, nullable=True)

    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    venue = relationship("Venue", back_populates="counting_events")
    gate = relationship("Gate", back_populates="counting_events")
