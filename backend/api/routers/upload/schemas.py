# api/schemas/upload.py

from pydantic import BaseModel, Field, UUID4
from typing import Optional, List
from datetime import datetime


class TagInput(BaseModel):
    """Tag input for media uploads"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    color: Optional[str] = Field(default='#3B82F6', pattern='^#[0-9A-Fa-f]{6}$')


class TagResponse(BaseModel):
    """Tag response"""
    id: int
    name: str
    description: Optional[str]
    color: str
    
    class Config:
        from_attributes = True


class VideoUploadResponse(BaseModel):
    """Response after video upload"""
    id: int
    video_id: UUID4
    filename: str
    storage_key: str
    storage_backend: str
    file_size_bytes: int
    duration_seconds: Optional[float]
    plant_site: str
    shift: Optional[str]
    inspection_line: Optional[str]
    recorded_at: datetime
    status: str
    tags: List[TagResponse] = []
    created_at: datetime
    
    class Config:
        from_attributes = True


class ImageUploadResponse(BaseModel):
    """Response after image upload"""
    id: int
    image_id: UUID4
    filename: str
    storage_key: str
    storage_backend: str
    file_size_bytes: int
    width: int
    height: int
    plant_site: str
    shift: Optional[str]
    inspection_line: Optional[str]
    captured_at: datetime
    video_id: Optional[UUID4]
    frame_number: Optional[int]
    checksum: Optional[str]
    tags: List[TagResponse] = []
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class DetectionCreateRequest(BaseModel):
    """Request to create a detection"""
    image_id: int
    bbox_x: float = Field(..., ge=0)
    bbox_y: float = Field(..., ge=0)
    bbox_width: float = Field(..., gt=0)
    bbox_height: float = Field(..., gt=0)
    bbox_format: str = Field(default='normalized', pattern='^(normalized|absolute)$')
    label: str = Field(..., min_length=1, max_length=100)
    confidence: float = Field(..., ge=0.0, le=1.0)
    tags: Optional[List[TagInput]] = None


class DetectionResponse(BaseModel):
    """Response after detection creation"""
    id: int
    detection_id: UUID4
    image_id: int
    bbox_x: float
    bbox_y: float
    bbox_width: float
    bbox_height: float
    bbox_format: str
    label: str
    confidence: float
    storage_key: Optional[str]
    storage_backend: Optional[str]
    checksum: Optional[str]
    embedding_generated: bool
    tags: List[TagResponse] = []
    created_at: datetime
    
    class Config:
        from_attributes = True


class BulkDetectionCreateRequest(BaseModel):
    """Bulk detection creation"""
    detections: List[DetectionCreateRequest] = Field(..., min_length=1, max_length=1000)


class BulkDetectionResponse(BaseModel):
    """Response after bulk detection creation"""
    total: int
    created: int
    failed: int
    detection_ids: List[int]
    errors: List[str]