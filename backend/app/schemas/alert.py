"""Alert Pydantic schemas."""

from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


class AlertResponse(BaseModel):
    id: str
    venue_id: str
    severity: str
    status: str
    title: str
    message: str
    recommended_action: Optional[str] = None
    occupancy_at_trigger: Optional[int] = None
    capacity_at_trigger: Optional[int] = None
    entry_rate_at_trigger: Optional[float] = None
    exit_rate_at_trigger: Optional[float] = None
    forecast_occupancy: Optional[int] = None
    trigger_reason: Optional[str] = None
    triggered_at: datetime
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_note: Optional[str] = None

    model_config = {"from_attributes": True}


class AlertAcknowledge(BaseModel):
    acknowledged_by: str = Field("admin", min_length=1)


class AlertResolve(BaseModel):
    resolved_by: str = Field("admin", min_length=1)
    resolution_note: Optional[str] = None
