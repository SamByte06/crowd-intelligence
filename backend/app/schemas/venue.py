"""Venue Pydantic schemas for request/response validation."""

from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from typing import Optional


class VenueCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    location: Optional[str] = None
    usable_area_sqm: Optional[float] = Field(None, gt=0)
    max_capacity: Optional[int] = Field(None, gt=0)
    density_per_sqm: float = Field(2.0, gt=0, le=10)
    warning_threshold: float = Field(0.75, gt=0, le=1.0)
    critical_threshold: float = Field(0.90, gt=0, le=1.0)
    timezone: str = "UTC"

    @field_validator("critical_threshold")
    @classmethod
    def critical_above_warning(cls, v, info):
        warning = info.data.get("warning_threshold", 0.75)
        if v <= warning:
            raise ValueError("Critical threshold must be greater than warning threshold")
        return v


class VenueUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    location: Optional[str] = None
    usable_area_sqm: Optional[float] = Field(None, gt=0)
    max_capacity: Optional[int] = Field(None, gt=0)
    density_per_sqm: Optional[float] = Field(None, gt=0, le=10)
    warning_threshold: Optional[float] = Field(None, gt=0, le=1.0)
    critical_threshold: Optional[float] = Field(None, gt=0, le=1.0)
    timezone: Optional[str] = None
    is_active: Optional[bool] = None


class VenueResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    location: Optional[str] = None
    usable_area_sqm: Optional[float] = None
    max_capacity: Optional[int] = None
    density_per_sqm: float
    warning_threshold: float
    critical_threshold: float
    current_occupancy: int
    total_entries: int
    total_exits: int
    baseline_established: bool
    baseline_established_at: Optional[datetime] = None
    baseline_established_by: Optional[str] = None
    effective_capacity: Optional[int] = None
    capacity_is_estimated: bool = False
    timezone: str
    is_active: bool
    monitoring_active: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class BaselineRequest(BaseModel):
    occupancy: int = Field(..., ge=0)
    established_by: str = Field("admin", min_length=1)
    reason: Optional[str] = None


class ReconcileRequest(BaseModel):
    verified_occupancy: int = Field(..., ge=0)
    performed_by: str = Field("admin", min_length=1)
    reason: str = Field(..., min_length=1)
