# api/schemas/search.py

from pydantic import BaseModel, Field, UUID4
from typing import Optional, List, Literal
from datetime import datetime


class BoundingBox(BaseModel):
    """Bounding box representation."""
    x: float
    y: float
    width: float
    height: float
    format: str = 'normalized'


class SearchFilterParams(BaseModel):
    """Common filter parameters for search."""
    plant_site: Optional[str] = None
    shift: Optional[str] = None
    inspection_line: Optional[str] = None
    labels: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    min_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    video_id: Optional[int] = None


class ImageSearchRequest(BaseModel):
    """Search by image request."""
    top_k: int = Field(default=10, ge=1, le=100)
    score_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    search_type: Literal['images', 'detections', 'both'] = 'detections'
    filters: Optional[SearchFilterParams] = None
    return_vectors: bool = False


class TextSearchRequest(BaseModel):
    """Search by text request."""
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(default=10, ge=1, le=100)
    score_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    search_type: Literal['images', 'detections', 'both'] = 'detections'
    filters: Optional[SearchFilterParams] = None
    return_vectors: bool = False


class HybridSearchRequest(BaseModel):
    """Hybrid search (image + text) request."""
    query: str = Field(..., min_length=1, max_length=500)
    text_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    top_k: int = Field(default=10, ge=1, le=100)
    score_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    search_type: Literal['images', 'detections', 'both'] = 'detections'
    filters: Optional[SearchFilterParams] = None
    return_vectors: bool = False


class SimilaritySearchRequest(BaseModel):
    """Find similar items to a given detection/image."""
    item_id: int = Field(..., description="Image or Detection ID")
    item_type: Literal['image', 'detection'] = 'detection'
    top_k: int = Field(default=10, ge=1, le=100)
    score_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    filters: Optional[SearchFilterParams] = None
    return_vectors: bool = False


class ImageSearchResult(BaseModel):
    """Image search result."""
    id: int
    image_id: UUID4
    filename: str
    storage_key: str
    similarity_score: float
    
    # Image metadata
    width: int
    height: int
    plant_site: str
    shift: Optional[str]
    inspection_line: Optional[str]
    captured_at: datetime
    
    # Video context
    video_id: Optional[int]
    video_uuid: Optional[UUID4]
    frame_number: Optional[int]
    timestamp_in_video: Optional[float]
    
    # Download URL
    download_url: Optional[str] = None
    
    # enable attribute loading (ORM style) in Pydantic v2
    model_config = {
        "from_attributes": True
    }


class DetectionSearchResult(BaseModel):
    """Detection search result."""
    id: int
    detection_id: UUID4
    similarity_score: float
    
    # Detection metadata
    label: str
    confidence: float
    bbox: BoundingBox
    
    # Image context
    image_id: int
    image_uuid: UUID4
    image_filename: str
    image_storage_key: str
    
    # Context metadata
    plant_site: str
    shift: Optional[str]
    inspection_line: Optional[str]
    captured_at: datetime
    
    # Video context
    video_id: Optional[int]
    video_uuid: Optional[UUID4]
    frame_number: Optional[int]
    timestamp_in_video: Optional[float]
    
    # Tags
    tags: List[str] = []
    
    # Download URLs
    image_url: Optional[str] = None
    crop_url: Optional[str] = None
    
    # enable attribute loading (ORM style) in Pydantic v2
    model_config = {
        "from_attributes": True
    }


class SearchResponse(BaseModel):
    """Search response."""
    query_id: UUID4
    search_type: str
    results_type: str  # 'images', 'detections', or 'both'
    
    # Results
    image_results: Optional[List[ImageSearchResult]] = None
    detection_results: Optional[List[DetectionSearchResult]] = None
    
    # Metadata
    total_results: int
    execution_time_ms: int
    filters_applied: dict
    model_version: str


class SearchHistoryItem(BaseModel):
    """Search history entry."""
    id: UUID4
    query_type: str
    query_text: Optional[str]
    search_type: str
    results_count: int
    execution_time_ms: int
    created_at: datetime
    
    # enable attribute loading (ORM style) in Pydantic v2
    model_config = {
        "from_attributes": True
    }


class SearchStatsResponse(BaseModel):
    """Search statistics."""
    total_searches: int
    searches_today: int
    avg_execution_time_ms: float
    most_searched_labels: List[dict]
    search_type_distribution: dict