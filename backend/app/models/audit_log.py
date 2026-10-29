"""Audit log database model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship

from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    venue_id = Column(String(36), ForeignKey("venues.id", ondelete="CASCADE"), nullable=True)

    action = Column(String(255), nullable=False)
    entity_type = Column(String(50), nullable=True)  # "venue", "gate", "baseline", etc.
    entity_id = Column(String(36), nullable=True)
    performed_by = Column(String(255), default="system")
    details = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # Relationship
    venue = relationship("Venue", back_populates="audit_logs")
