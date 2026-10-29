"""Common schema types."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    cameras_active: int
    uptime_seconds: float
