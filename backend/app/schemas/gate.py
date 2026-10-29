"""Gate Pydantic schemas."""

from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


class GateCreate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=255)
    gate_type: str = Field(..., pattern="^(ENTRY|EXIT)$")
    camera_source_type: str = Field("WEBCAM", pattern="^(WEBCAM|VIDEO_FILE|RTSP|HTTP)$")
    camera_source: str = Field("0")
    camera_username: Optional[str] = None
    camera_password: Optional[str] = None
    line_start_x: float = Field(0.0, ge=0.0, le=1.0)
    line_start_y: float = Field(0.5, ge=0.0, le=1.0)
    line_end_x: float = Field(1.0, ge=0.0, le=1.0)
    line_end_y: float = Field(0.5, ge=0.0, le=1.0)
    counting_direction: str = Field("down", pattern="^(up|down|left|right)$")
    confidence_threshold: float = Field(0.25, gt=0.0, le=1.0)
    frame_skip: int = Field(1, ge=1, le=30)
    is_enabled: bool = True


class GateUpdate(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=255)
    gate_type: Optional[str] = Field(None, pattern="^(ENTRY|EXIT)$")
    camera_source_type: Optional[str] = Field(None, pattern="^(WEBCAM|VIDEO_FILE|RTSP|HTTP)$")
    camera_source: Optional[str] = None
    camera_username: Optional[str] = None
    camera_password: Optional[str] = None
    line_start_x: Optional[float] = Field(None, ge=0.0, le=1.0)
    line_start_y: Optional[float] = Field(None, ge=0.0, le=1.0)
    line_end_x: Optional[float] = Field(None, ge=0.0, le=1.0)
    line_end_y: Optional[float] = Field(None, ge=0.0, le=1.0)
    counting_direction: Optional[str] = Field(None, pattern="^(up|down|left|right)$")
    confidence_threshold: Optional[float] = Field(None, gt=0.0, le=1.0)
    frame_skip: Optional[int] = Field(None, ge=1, le=30)
    is_enabled: Optional[bool] = None


class GateResponse(BaseModel):
    id: str
    venue_id: str
    display_name: str
    gate_type: str
    camera_source_type: str
    camera_source: str
    # Credentials never exposed
    line_start_x: float
    line_start_y: float
    line_end_x: float
    line_end_y: float
    counting_direction: str
    confidence_threshold: float
    frame_skip: int
    is_enabled: bool
    status: str
    last_frame_at: Optional[datetime] = None
    last_count_at: Optional[datetime] = None
    error_message: Optional[str] = None
    reconnect_attempts: int = 0
    entry_count: int = 0
    exit_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
