"""Occupancy, flow, and forecast schemas."""

from datetime import datetime
from pydantic import BaseModel
from typing import Optional


class OccupancyResponse(BaseModel):
    venue_id: str
    current_occupancy: int
    effective_capacity: Optional[int] = None
    capacity_is_estimated: bool = False
    remaining_capacity: Optional[int] = None
    occupancy_percentage: Optional[float] = None
    total_entries: int
    total_exits: int
    baseline_established: bool
    occupancy_is_uncertain: bool = False
    reconciliation_needed: bool = False
    last_updated: Optional[datetime] = None


class FlowRateResponse(BaseModel):
    venue_id: str
    window_seconds: int
    entry_rate_per_min: float
    exit_rate_per_min: float
    net_inflow_per_min: float
    total_entries_in_window: int
    total_exits_in_window: int
    measured_at: datetime


class ForecastPoint(BaseModel):
    horizon_minutes: int
    forecast_occupancy: int
    is_above_warning: bool = False
    is_above_critical: bool = False
    is_above_capacity: bool = False


class ForecastResponse(BaseModel):
    venue_id: str
    current_occupancy: int
    net_inflow_rate: float
    effective_capacity: Optional[int] = None
    time_to_warning_minutes: Optional[float] = None
    time_to_critical_minutes: Optional[float] = None
    time_to_capacity_minutes: Optional[float] = None
    forecasts: list[ForecastPoint]
    data_quality: str  # "good", "degraded", "insufficient"
    measured_at: datetime


class GateCountResponse(BaseModel):
    gate_id: str
    display_name: str
    gate_type: str
    entry_count: int
    exit_count: int
    status: str


class EventResponse(BaseModel):
    id: str
    venue_id: str
    gate_id: str
    direction: str
    track_id: Optional[int] = None
    confidence: Optional[float] = None
    timestamp: datetime

    model_config = {"from_attributes": True}
