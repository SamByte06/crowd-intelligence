"""Occupancy baseline and snapshot models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, Text

from app.database import Base


class OccupancyBaseline(Base):
    """Records each time the occupancy baseline is established or corrected."""
    __tablename__ = "occupancy_baselines"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    venue_id = Column(String(36), ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)

    occupancy_value = Column(Integer, nullable=False)
    established_by = Column(String(255), default="admin")
    reason = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationship
    from sqlalchemy.orm import relationship
    venue = relationship("Venue", back_populates="occupancy_baselines")


class OccupancySnapshot(Base):
    """Periodic snapshots of venue occupancy state for time-series queries."""
    __tablename__ = "occupancy_snapshots"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    venue_id = Column(String(36), ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)

    occupancy = Column(Integer, nullable=False)
    total_entries = Column(Integer, default=0)
    total_exits = Column(Integer, default=0)
    entry_rate = Column(Float, default=0.0)
    exit_rate = Column(Float, default=0.0)
    net_inflow = Column(Float, default=0.0)
    capacity_utilization = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # Relationship
    from sqlalchemy.orm import relationship
    venue = relationship("Venue", back_populates="occupancy_snapshots")
