from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ─────────────────────────── Camera ──────────────────────────── #

class WasteCameraCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    location: str = Field(..., min_length=1, max_length=200)
    plant_site: str = ""
    stream_type: Literal['rtsp', 'mjpeg', 'upload']
    stream_url: str = Field("", max_length=500)
    target_fps: float = Field(2.0, ge=0.1, le=30.0)


class WasteCameraUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    location: Optional[str] = Field(None, min_length=1, max_length=200)
    plant_site: Optional[str] = None
    stream_type: Optional[Literal['rtsp', 'mjpeg', 'upload']] = None
    stream_url: Optional[str] = Field(None, max_length=500)
    target_fps: Optional[float] = Field(None, ge=0.1, le=30.0)
    is_active: Optional[bool] = None


class WasteCameraResponse(BaseModel):
    id: int
    camera_uuid: UUID
    name: str
    location: str
    plant_site: str
    stream_type: str
    stream_url: str
    target_fps: float
    is_active: bool
    status: str
    consecutive_high: int
    last_frame_at: Optional[datetime]
    last_risk_level: str
    created_at: datetime


# ──────────────────────── Inspections ────────────────────────── #

class InspectFrameRequest(BaseModel):
    camera_uuid: UUID
    image_b64: str = Field(..., min_length=1, description="Base64-encoded JPEG frame")
    async_mode: bool = Field(True, description="True=Celery task, False=synchronous response")


class WasteComposition(BaseModel):
    plastic: float = 0.0
    paper: float = 0.0
    glass: float = 0.0
    metal: float = 0.0
    organic: float = 0.0
    e_waste: float = 0.0
    hazardous: float = 0.0
    other: float = 0.0


class ContaminationItem(BaseModel):
    item: str
    severity: Literal['low', 'medium', 'high', 'critical']
    location_in_frame: str
    action: str


class WasteInspectionResponse(BaseModel):
    id: int
    inspection_uuid: UUID
    camera_uuid: UUID
    sequence_no: int
    frame_timestamp: datetime
    waste_composition: WasteComposition
    contamination_alerts: List[ContaminationItem]
    line_blockage: bool
    overall_risk: Literal['low', 'medium', 'high', 'critical']
    confidence: float
    inspector_note: str
    vlm_provider: str
    vlm_model: str
    processing_time_ms: Optional[int]
    created_at: datetime


# ──────────────────────────── Alerts ─────────────────────────── #

class WasteAlertResponse(BaseModel):
    id: int
    alert_uuid: UUID
    camera_uuid: UUID
    alert_type: Literal['contamination', 'blockage', 'escalation', 'drift']
    severity: Literal['low', 'medium', 'high', 'critical']
    details: dict
    is_acknowledged: bool
    acknowledged_at: Optional[datetime]
    created_at: datetime


# ────────────────────────── Statistics ───────────────────────── #

class RiskBreakdown(BaseModel):
    low: int = 0
    medium: int = 0
    high: int = 0
    critical: int = 0


class WasteStats(BaseModel):
    total_inspections: int
    risk_breakdown: RiskBreakdown
    top_contamination_labels: List[Dict]
    avg_confidence_by_camera: List[Dict]
    active_cameras: int
    alerts_last_24h: int


# ─────────────────────────── Pagination ──────────────────────── #

class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool


class PaginatedCameras(BaseModel):
    items: List[WasteCameraResponse]
    pagination: PaginationMeta


class PaginatedInspections(BaseModel):
    items: List[WasteInspectionResponse]
    pagination: PaginationMeta


class PaginatedAlerts(BaseModel):
    items: List[WasteAlertResponse]
    pagination: PaginationMeta
