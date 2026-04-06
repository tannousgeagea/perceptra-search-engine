# api/schemas/media.py

from pydantic import BaseModel, Field, UUID4
from typing import Optional, List, Literal
from datetime import datetime


class MediaFilterParams(BaseModel):
    """Filter parameters for media queries."""
    # Search
    search: Optional[str] = Field(default=None, description="Search in filename")
    
    # Filters
    plant_site: Optional[str] = None
    shift: Optional[str] = None
    inspection_line: Optional[str] = None
    status: Optional[str] = None
    
    # Tags
    tags: Optional[List[str]] = Field(default=None, description="Filter by tag names")
    tags_match: Literal['any', 'all'] = Field(default='any', description="Match any or all tags")
    
    # Date range
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    
    # Video-specific
    has_detections: Optional[bool] = None
    min_duration: Optional[float] = None
    max_duration: Optional[float] = None
    
    # Image-specific
    is_video_frame: Optional[bool] = None
    video_id: Optional[int] = None
    
    # Detection-specific
    labels: Optional[List[str]] = None
    min_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    embedding_generated: Optional[bool] = None
    
    # Sorting
    sort_by: Literal[
        'created_at', 'captured_at', 'recorded_at',
        'filename', 'confidence', 'size'
    ] = 'created_at'
    sort_order: Literal['asc', 'desc'] = 'desc'
    
    # Pagination
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class TagResponse(BaseModel):
    """Tag response."""
    id: int
    name: str
    description: Optional[str]
    color: str
    usage_count: Optional[dict] = None
    
    # enable attribute loading (ORM style) in Pydantic v2
    model_config = {
        "from_attributes": True
    }


class VideoResponse(BaseModel):
    """Video response with all details."""
    id: int
    video_id: UUID4
    filename: str
    storage_key: str
    storage_backend: str
    file_size_bytes: int
    duration_seconds: Optional[float]
    
    # Metadata
    plant_site: str
    shift: Optional[str]
    inspection_line: Optional[str]
    recorded_at: datetime
    
    # Status
    status: str
    
    # Counts
    frame_count: int
    detection_count: int
    
    # Tags
    tags: List[TagResponse]
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    # Download URL
    download_url: Optional[str] = None
    
    # enable attribute loading (ORM style) in Pydantic v2
    model_config = {
        "from_attributes": True
    }


class ImageResponse(BaseModel):
    """Image response with all details."""
    id: int
    image_id: UUID4
    filename: str
    storage_key: str
    storage_backend: str
    file_size_bytes: int
    
    # Dimensions
    width: int
    height: int
    
    # Metadata
    plant_site: str
    shift: Optional[str]
    inspection_line: Optional[str]
    captured_at: datetime
    
    # Video context
    video_id: Optional[int]
    video_uuid: Optional[UUID4]
    frame_number: Optional[int]
    timestamp_in_video: Optional[float]
    
    # Status
    status: str
    checksum: Optional[str]
    
    # Counts
    detection_count: int
    
    # Tags
    tags: List[TagResponse]
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    # URLs
    download_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    
    # enable attribute loading (ORM style) in Pydantic v2
    model_config = {
        "from_attributes": True
    }


class DetectionResponse(BaseModel):
    """Detection response with all details."""
    id: int
    detection_id: UUID4
    
    # Detection data
    label: str
    confidence: float
    bbox_x: float
    bbox_y: float
    bbox_width: float
    bbox_height: float
    bbox_format: str
    
    # Image context
    image_id: int
    image_uuid: UUID4
    image_filename: str
    image_width: int
    image_height: int
    
    # Metadata
    plant_site: str
    shift: Optional[str]
    inspection_line: Optional[str]
    captured_at: datetime
    
    # Video context
    video_id: Optional[int]
    video_uuid: Optional[UUID4]
    
    # Embedding
    embedding_generated: bool
    embedding_model_version: Optional[str]
    
    # Tags
    tags: List[TagResponse]
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    # URLs
    image_url: Optional[str] = None
    crop_url: Optional[str] = None
    
    # enable attribute loading (ORM style) in Pydantic v2
    model_config = {
        "from_attributes": True
    }


class PaginationMetadata(BaseModel):
    """Pagination metadata."""
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool


class VideoListResponse(BaseModel):
    """Paginated video list response."""
    items: List[VideoResponse]
    pagination: PaginationMetadata
    filters_applied: dict


class ImageListResponse(BaseModel):
    """Paginated image list response."""
    items: List[ImageResponse]
    pagination: PaginationMetadata
    filters_applied: dict


class DetectionListResponse(BaseModel):
    """Paginated detection list response."""
    items: List[DetectionResponse]
    pagination: PaginationMetadata
    filters_applied: dict


class LabelCount(BaseModel):
    label: str
    count: int

class PlantBreakdown(BaseModel):
    plant_site: str
    total: int
    detections: int

class MediaStatsResponse(BaseModel):
    """Media library statistics."""
    total_videos: int
    total_images: int
    total_detections: int
    total_storage_bytes: int
    videos_by_status: dict
    images_by_status: dict
    detections_by_label: List[dict]
    top_labels: List[LabelCount] = []
    plant_breakdown: List[PlantBreakdown] = []
    recent_uploads: dict
    media_trend_pct: int = 0



# ---------------------------------------------------------------------------
# Schemas Media Ledger
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Bulk Operations
# ---------------------------------------------------------------------------

class BulkDeleteRequest(BaseModel):
    ids: List[int] = Field(..., min_length=1, max_length=500)

class BulkDeleteResponse(BaseModel):
    deleted: int
    failed: int = 0

class BulkTagRequest(BaseModel):
    ids: List[int] = Field(..., min_length=1, max_length=500)
    tag_names: List[str] = Field(..., min_length=1)
    action: Literal['add', 'remove']

class BulkTagResponse(BaseModel):
    updated: int
    tags: List[str]


class MediaLedgerItem(BaseModel):
    id: int
    media_id: str
    media_type: str
    storage_backend: str
    storage_key: str
    filename: str
    file_size_bytes: int
    file_size_mb: float
    content_type: str
    file_format: str
    checksum: Optional[str]
    status: str
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MediaLedgerListResponse(BaseModel):
    items: List[MediaLedgerItem]
    pagination: dict
    filters_applied: dict