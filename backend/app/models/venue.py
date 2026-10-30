"""Venue database model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Venue(Base):
    __tablename__ = "venues"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    location = Column(String(255), nullable=True)

    # Capacity configuration
    usable_area_sqm = Column(Float, nullable=True)
    max_capacity = Column(Integer, nullable=True)  # Admin-provided; null = use estimate
    density_per_sqm = Column(Float, default=2.0)
    moderate_threshold = Column(Float, default=0.60)  # fraction of capacity (Moderate Crowd)
    warning_threshold = Column(Float, default=0.75)   # fraction of capacity (High Rush)
    critical_threshold = Column(Float, default=0.90)  # fraction of capacity (Critical Capacity)

    # Notification Campaign & Background Reminder Settings
    notification_campaign_active = Column(Boolean, default=True)
    reminder_interval_seconds = Column(Integer, default=60)  # default 60s background reminder interval

    # Current state
    current_occupancy = Column(Integer, default=0)
    total_entries = Column(Integer, default=0)
    total_exits = Column(Integer, default=0)
    baseline_established = Column(Boolean, default=False)
    baseline_established_at = Column(DateTime, nullable=True)
    baseline_established_by = Column(String(255), nullable=True)

    # Settings
    timezone = Column(String(50), default="UTC")
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    gates = relationship("Gate", back_populates="venue", cascade="all, delete-orphan")
    counting_events = relationship("CountingEvent", back_populates="venue", cascade="all, delete-orphan")
    occupancy_baselines = relationship("OccupancyBaseline", back_populates="venue", cascade="all, delete-orphan")
    occupancy_snapshots = relationship("OccupancySnapshot", back_populates="venue", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="venue", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="venue", cascade="all, delete-orphan")
    push_subscriptions = relationship("PushSubscription", back_populates="venue", cascade="all, delete-orphan")
    notification_history = relationship("NotificationHistory", back_populates="venue", cascade="all, delete-orphan")

    @property
    def effective_capacity(self) -> int | None:
        """Return admin-provided capacity or area-based estimate."""
        if self.max_capacity is not None:
            return self.max_capacity
        if self.usable_area_sqm is not None and self.density_per_sqm:
            return int(self.usable_area_sqm * self.density_per_sqm)
        return None

    @property
    def capacity_is_estimated(self) -> bool:
        return self.max_capacity is None and self.usable_area_sqm is not None
