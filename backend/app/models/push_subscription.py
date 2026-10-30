"""Push Subscription and Notification History database models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.database import Base


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    venue_id = Column(String(36), ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint = Column(Text, nullable=False, index=True)
    p256dh = Column(Text, nullable=False)
    auth = Column(Text, nullable=False)

    user_identifier = Column(String(255), nullable=True)  # guest session or user ID
    is_following = Column(Boolean, default=True)
    notifications_enabled = Column(Boolean, default=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    last_notified_at = Column(DateTime, nullable=True)

    # Relationship
    venue = relationship("Venue", back_populates="push_subscriptions")


class NotificationHistory(Base):
    __tablename__ = "notification_history"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    venue_id = Column(String(36), ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    severity = Column(String(50), nullable=False)  # NORMAL, MODERATE, HIGH, CRITICAL
    tag = Column(String(100), nullable=True)

    subscribers_count = Column(Integer, default=0)
    successful_deliveries = Column(Integer, default=0)
    failed_deliveries = Column(Integer, default=0)

    triggered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationship
    venue = relationship("Venue", back_populates="notification_history")
