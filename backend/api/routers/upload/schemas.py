# api/schemas/detection.py

from pydantic import BaseModel, UUID4, Field
from typing import Optional
from datetime import datetime

class DetectionCreate(BaseModel):
    image_id: UUID4
    bbox_x: float
    bbox_y: float
    bbox_width: float
    bbox_height: float
    bbox_format: str = 'normalized'
    label: str
    confidence: float = Field(ge=0.0, le=1.0)


class DetectionResponse(BaseModel):
    id: UUID4
    image_id: UUID4
    bbox_x: float
    bbox_y: float
    bbox_width: float
    bbox_height: float
    label: str
    confidence: float
    embedding_generated: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class VideoUploadRequest(BaseModel):
    filename: str
    plant_site: str
    shift: Optional[str] = None
    inspection_line: Optional[str] = None
    recorded_at: datetime


class VideoResponse(BaseModel):
    id: UUID4
    filename: str
    file_path: str
    plant_site: str
    status: str
    recorded_at: datetime
    created_at: datetime
    
    class Config:
        from_attributes = True