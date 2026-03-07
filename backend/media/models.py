# apps/media/models.py

from django.db import models
from tenants.models import Tenant
from tenants.managers import TenantManager
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

User = get_user_model()
import uuid


class StorageBackend(models.TextChoices):
    """Supported storage backend types."""
    AZURE = 'azure', _('Azure Blob Storage')
    S3 = 's3', _('Amazon S3')
    MINIO = 'minio', _('MinIO / S3-compatible')
    LOCAL = 'local', _('Local Filesystem')

class StatusChoices(models.TextChoices):
    """Standard status choices for processing state."""
    UPLOADED = 'uploaded', _('Uploaded')
    PROCESSING = 'processing', _('Processing')
    COMPLETED = 'completed', _('Completed')
    FAILED = 'failed', _('Failed')

class TenantScopedModel(models.Model):
    """Abstract base for tenant-scoped models"""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_index=True)

    objects = TenantManager()
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    # user
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_created",
        help_text="User who created this record"
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_updated",
        help_text="User who last updated this record"
    )


    class Meta:
        abstract = True


class Video(TenantScopedModel):
    """Video file from inspection"""
    video_id = models.UUIDField(default=uuid.uuid4, editable=False)
    
    # File info
    filename = models.CharField(max_length=255)
    file_size_bytes = models.BigIntegerField()
    duration_seconds = models.FloatField(null=True)
    
    # Metadata
    plant_site = models.CharField(max_length=100, db_index=True)
    shift = models.CharField(max_length=50, null=True, blank=True)
    inspection_line = models.CharField(max_length=100, null=True, blank=True)
    recorded_at = models.DateTimeField(db_index=True)
    
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default='uploaded', db_index=True)
    
    storage_backend = models.CharField(
        max_length=20,
        choices=StorageBackend.choices,
        default=StorageBackend.LOCAL,
        help_text=_('Storage backend type')
    )

    storage_key = models.CharField(
        max_length=500,
        blank=True,
        help_text=_('Full path/key in storage (e.g., org-123/images/2025/img.jpg)')
    )

    # Checksum for integrity verification
    checksum = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text=_('SHA-256 checksum of file')
    )

    file_format = models.CharField(
        max_length=10,
        help_text=_('Image format (mp4, avi, mov, webm, etc.)')
    )

    tags = models.ManyToManyField('Tag', through='VideoTag', related_name='videos', blank=True)

    class Meta:
        db_table = 'videos'
        indexes = [
            models.Index(fields=['tenant', 'recorded_at']),
            models.Index(fields=['tenant', 'plant_site']),
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['storage_backend', 'storage_key']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-recorded_at']
        unique_together = [('tenant', 'storage_key')]
        default_manager_name = 'objects'


    def __str__(self) -> str:
        return f"Video {self.filename} ({self.duration_seconds:.2f}s)"
    
    def clean(self):
        """Custom validation to ensure data integrity."""
        if self.file_size_bytes < 0:
            raise ValidationError({'file_size_bytes': _('File size cannot be negative.')})
        if self.duration_seconds is not None and self.duration_seconds < 0:
            raise ValidationError({'duration_seconds': _('Duration cannot be negative.')})
    
    def save(self, *args, **kwargs):
        """Override save to include validation."""
        self.full_clean()  # This will call the clean() method
        super().save(*args, **kwargs)
    
    @property
    def file_size_mb(self) -> float:
        """Get file size in megabytes."""
        if self.file_size_bytes is not None:
            return self.file_size_bytes / (1024 * 1024)
        return 0.0
    
    @property
    def duration_minutes(self) -> float:
        """Get duration in minutes."""
        if self.duration_seconds is not None:
            return self.duration_seconds / 60
        return 0.0
    
    @property
    def frame_rate(self) -> float:
        """Calculate frame rate if possible."""
        if self.duration_seconds and self.duration_seconds > 0:
            # Assuming we have a way to get total frames (not stored in model)
            total_frames = self.frames.count()  # type: ignore
            return total_frames / self.duration_seconds
        return 0.0
    
    @property
    def resolution(self) -> str:
        """Get resolution of the video based on its frames."""
        if self.frames.exists():   # type: ignore
            # Assuming all frames have the same resolution, we can take the first one
            first_frame = self.frames.first() # type: ignore
            return f"{first_frame.width}x{first_frame.height}"
        return "Unknown"
    
    @property
    def aspect_ratio(self) -> float:
        """Calculate aspect ratio based on first frame."""
        if self.frames.exists():  # type: ignore
            first_frame = self.frames.first() # type: ignore
            if first_frame.height > 0:
                return first_frame.width / first_frame.height
        return 0.0
    
    @property
    def megapixels(self) -> float:
        """Calculate megapixels based on first frame."""
        if self.frames.exists():   # type: ignore
            first_frame = self.frames.first() # type: ignore
            return (first_frame.width * first_frame.height) / 1_000_000
        return 0.0
    
    @property
    def frame_count(self) -> int:
        """Get total number of frames extracted from this video."""
        return self.frames.count()  #type: ignore
    
    def get_frame_by_timestamp(self, timestamp: float) -> 'Image':
        """Retrieve a frame closest to the given timestamp."""
        return self.frames.filter(timestamp_in_video__lte=timestamp).order_by('-timestamp_in_video').first()  # type: ignore

    def get_frame_by_number(self, frame_number: int) -> 'Image':
        """Retrieve a frame by its frame number."""
        return self.frames.filter(frame_number=frame_number).first()  # type: ignore
    
    def get_detections(self):
        """Get all detections associated with this video."""
        return Detection.objects.filter(image__video=self)
    
    def get_download_url(self) -> str:
        """Generate a pre-signed URL for downloading the video."""
        # This is a placeholder implementation. In a real system, you would integrate with your storage backend.
        if self.storage_backend == StorageBackend.S3:
            return f"https://s3.amazonaws.com/{self.storage_key}?presigned=true"
        elif self.storage_backend == StorageBackend.AZURE:
            return f"https://azure.blob.core.windows.net/{self.storage_key}?sas_token=true"
        elif self.storage_backend == StorageBackend.MINIO:
            return f"https://minio.example.com/{self.storage_key}?presigned=true"
        elif self.storage_backend == StorageBackend.LOCAL:
            return f"/media/{self.storage_key}"
        else:
            return ""

class Image(TenantScopedModel):
    """Still image or extracted video frame"""
    image_id = models.UUIDField(default=uuid.uuid4, editable=False)
    
    # Relationship
    video = models.ForeignKey(Video, on_delete=models.CASCADE, null=True, blank=True, related_name='frames')
    
    # File info
    filename = models.CharField(max_length=255)
    file_size_bytes = models.BigIntegerField()
    
    # Image properties
    width = models.IntegerField()
    height = models.IntegerField()
    
    # Video frame info (null if standalone image)
    frame_number = models.IntegerField(null=True, blank=True)
    timestamp_in_video = models.FloatField(null=True, blank=True)  # seconds
    
    # Metadata
    plant_site = models.CharField(max_length=100, db_index=True)
    shift = models.CharField(max_length=50, null=True, blank=True)
    inspection_line = models.CharField(max_length=100, null=True, blank=True)
    captured_at = models.DateTimeField(db_index=True)
    
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default='uploaded', db_index=True)
    
    storage_backend = models.CharField(
        max_length=20,
        choices=StorageBackend.choices,
        default=StorageBackend.LOCAL,
        help_text=_('Storage backend type')
    )

    storage_key = models.CharField(
        max_length=500,
        blank=True,
        help_text=_('Full path/key in storage (e.g., org-123/images/2025/img.jpg)')
    )

    # Checksum for integrity verification
    checksum = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text=_('SHA-256 checksum of file')
    )

    file_format = models.CharField(
        max_length=10,
        help_text=_('Image format (jpg, png, tiff, etc.)')
    )
    
    tags = models.ManyToManyField('Tag', through='ImageTag', related_name='images', blank=True)

    class Meta:
        db_table = 'images'
        indexes = [
            models.Index(fields=['tenant', 'captured_at']),
            models.Index(fields=['tenant', 'plant_site']),
            models.Index(fields=['video', 'frame_number']),
            models.Index(fields=['storage_backend', 'storage_key']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-captured_at']
        unique_together = [('tenant', 'storage_key')]
        default_manager_name = 'objects'

    def __str__(self) -> str:
        return f"Image {self.filename} ({self.width}x{self.height})"

    @property
    def aspect_ratio(self) -> float:
        """Calculate image aspect ratio."""
        if self.height > 0:
            return self.width / self.height
        return 0.0
    
    @property
    def megapixels(self) -> float:
        """Calculate megapixels."""
        return (self.width * self.height) / 1_000_000
    
    @property
    def file_size_mb(self) -> float:
        """Get file size in megabytes."""
        if self.file_size_bytes is not None:
                return self.file_size_bytes / (1024 * 1024)
        return 0.0
    
    def get_download_url(self) -> str:
        """Generate a pre-signed URL for downloading the image."""
        # This is a placeholder implementation. In a real system, you would integrate with your storage backend.
        if self.storage_backend == StorageBackend.S3:
            return f"https://s3.amazonaws.com/{self.storage_key}?presigned=true"
        elif self.storage_backend == StorageBackend.AZURE:
            return f"https://azure.blob.core.windows.net/{self.storage_key}?sas_token=true"
        elif self.storage_backend == StorageBackend.MINIO:
            return f"https://minio.example.com/{self.storage_key}?presigned=true"
        elif self.storage_backend == StorageBackend.LOCAL:
            return f"/media/{self.storage_key}"
        else:
            return ""
        
    @property
    def get_detections(self):
        """Get all detections associated with this image."""
        return self.detections.all()   #type: ignore
    
    def get_tags(self):
        """Get all tags associated with this image."""
        return self.tags.all()
    
    def clean(self):
        """Custom validation to ensure data integrity."""
        if self.file_size_bytes < 0:
            raise ValidationError({'file_size_bytes': _('File size cannot be negative.')})
        if self.width < 0:
            raise ValidationError({'width': _('Width cannot be negative.')})
        if self.height < 0:
            raise ValidationError({'height': _('Height cannot be negative.')})
        
    def save(self, *args, **kwargs):
        """Override save to include validation."""
        self.full_clean()  # This will call the clean() method
        super().save(*args, **kwargs)
    
    @property
    def frame_info(self) -> str:
        """Return a string with frame information if this image is a video frame."""
        if self.video and self.frame_number is not None and self.timestamp_in_video is not None:
            return f"Frame {self.frame_number} at {self.timestamp_in_video:.2f}s"
        return "Not a video frame"
    
    @property
    def resolution(self) -> str:
        """Get resolution of the image."""
        return f"{self.width}x{self.height}"
    
    @property
    def dimensions(self) -> str:
        """Get dimensions of the image."""
        return f"{self.width}x{self.height}"
    


class Detection(TenantScopedModel):
    """Individual impurity detection (ROI)"""
    detection_id = models.UUIDField(default=uuid.uuid4, editable=False)
    
    # Relationship
    image = models.ForeignKey(Image, on_delete=models.CASCADE, related_name='detections')
    
    # Bounding box (normalized 0-1 or absolute pixels)
    bbox_x = models.FloatField()
    bbox_y = models.FloatField()
    bbox_width = models.FloatField()
    bbox_height = models.FloatField()
    bbox_format = models.CharField(max_length=20, default='normalized')  # 'normalized' or 'absolute'
    
    # Classification
    label = models.CharField(max_length=100, db_index=True)
    confidence = models.FloatField()
    
    # Cropped region (optional, for faster retrieval)
    storage_key = models.CharField(
        max_length=500,
        help_text=_('Full path/key in storage (e.g., org-123/images/2025/img.jpg)')
    )
    
    storage_backend = models.CharField(
        max_length=20,
        choices=StorageBackend.choices,
        default=StorageBackend.LOCAL,
        help_text=_('Storage backend type')
    )

    storage_key = models.CharField(
        max_length=500,
        blank=True,
        help_text=_('Full path/key in storage (e.g., org-123/images/2025/img.jpg)')
    )

    # Checksum for integrity verification
    checksum = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text=_('SHA-256 checksum of file')
    )

    tags = models.ManyToManyField('Tag', through='DetectionTag', related_name='detections', blank=True)

    # Vector DB reference
    vector_point_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    embedding_generated = models.BooleanField(default=False, db_index=True)
    embedding_model_version = models.CharField(max_length=50, null=True, blank=True)
    
    class Meta:
        db_table = 'detections'
        indexes = [
            models.Index(fields=['tenant', 'label']),
            models.Index(fields=['tenant', 'embedding_generated']),
            models.Index(fields=['image', 'confidence']),
            models.Index(fields=['vector_point_id']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']
        default_manager_name = 'objects'

    def __str__(self) -> str:
        return f"Detection {self.label} ({self.confidence:.2f}) in Image {self.image.filename}"
    
    def get_download_url(self) -> str:
        """Generate a pre-signed URL for downloading the cropped detection image."""
        # This is a placeholder implementation. In a real system, you would integrate with your storage backend.
        if self.storage_backend == StorageBackend.S3:
            return f"https://s3.amazonaws.com/{self.storage_key}?presigned=true"
        elif self.storage_backend == StorageBackend.AZURE:
            return f"https://azure.blob.core.windows.net/{self.storage_key}?sas_token=true"
        elif self.storage_backend == StorageBackend.MINIO:
            return f"https://minio.example.com/{self.storage_key}?presigned=true"
        elif self.storage_backend == StorageBackend.LOCAL:
            return f"/media/{self.storage_key}"
        else:
            return ""
    
    def clean(self):
        """Custom validation to ensure data integrity."""
        if self.confidence < 0 or self.confidence > 1:
            raise ValidationError({'confidence': _('Confidence must be between 0 and 1.')})
        if self.bbox_width < 0 or self.bbox_height < 0:
            raise ValidationError({'bbox_width': _('Bounding box width cannot be negative.'),
                                   'bbox_height': _('Bounding box height cannot be negative.')})
        if self.bbox_format not in ['normalized', 'absolute']:
            raise ValidationError({'bbox_format': _('Bounding box format must be either "normalized" or "absolute".')})
        if self.bbox_format == 'normalized':
            if not (0 <= self.bbox_x <= 1 and 0 <= self.bbox_y <= 1 and 0 <= self.bbox_width <= 1 and 0 <= self.bbox_height <= 1):
                raise ValidationError({'bbox_x': _('For normalized format, bbox values must be between 0 and 1.'),
                                       'bbox_y': _('For normalized format, bbox values must be between 0 and 1.'),
                                       'bbox_width': _('For normalized format, bbox values must be between 0 and 1.'),
                                       'bbox_height': _('For normalized format, bbox values must be between 0 and 1.')})
        super().clean()

    def save(self, *args, **kwargs):
        """Override save to include validation."""
        self.full_clean()  # This will call the clean() method
        super().save(*args, **kwargs)

    @property
    def absolute_bbox(self):
        """Convert bounding box to absolute pixel values if stored as normalized."""
        if self.bbox_format == 'absolute':
            return self.bbox_x, self.bbox_y, self.bbox_width, self.bbox_height
        elif self.bbox_format == 'normalized' and self.image:
            abs_x = int(self.bbox_x * self.image.width)
            abs_y = int(self.bbox_y * self.image.height)
            abs_width = int(self.bbox_width * self.image.width)
            abs_height = int(self.bbox_height * self.image.height)
            return abs_x, abs_y, abs_width, abs_height
        else:
            raise ValueError("Cannot convert bbox to absolute without valid image reference.")
        
    @property
    def normalized_bbox(self):
        """Convert bounding box to normalized values if stored as absolute."""
        if self.bbox_format == 'normalized':
            return self.bbox_x, self.bbox_y, self.bbox_width, self.bbox_height
        elif self.bbox_format == 'absolute' and self.image:
            norm_x = self.bbox_x / self.image.width
            norm_y = self.bbox_y / self.image.height
            norm_width = self.bbox_width / self.image.width
            norm_height = self.bbox_height / self.image.height
            return norm_x, norm_y, norm_width, norm_height
        else:
            raise ValueError("Cannot convert bbox to normalized without valid image reference.")
        
    @property
    def vector_representation(self):
        """Placeholder method to get vector representation for this detection."""
        # In a real implementation, this would interface with your embedding generation logic
        if self.embedding_generated:
            return {
                'vector_point_id': self.vector_point_id,
                'embedding_model_version': self.embedding_model_version
            }
        else:
            return None

    def generate_embedding(self, model_version: str):
        """Placeholder method to generate embedding for this detection."""
        # In a real implementation, this would call your embedding generation service
        self.vector_point_id = f"vec-{self.detection_id}"
        self.embedding_generated = True
        self.embedding_model_version = model_version
        self.save()

    def clear_embedding(self):
        """Clear embedding information for this detection."""
        self.vector_point_id = None
        self.embedding_generated = False
        self.embedding_model_version = None
        self.save()

    @property
    def has_embedding(self) -> bool:
        """Check if this detection has an embedding generated."""
        return self.embedding_generated and self.vector_point_id is not None

    @property
    def embedding_info(self):
        """Get embedding information for this detection."""
        if self.has_embedding:
            return {
                'vector_point_id': self.vector_point_id,
                'embedding_model_version': self.embedding_model_version
            }
        return None
    
    @property
    def embedding_vector(self):
        """Placeholder method to retrieve the actual embedding vector."""
        # In a real implementation, this would retrieve the vector from your vector database
        if self.has_embedding:
            return [0.0] * 512  # Example: return a dummy 512-dimensional vector
        return None

    @property
    def tags_list(self):
        """Get a list of tag names associated with this detection."""
        return list(self.tags.values_list('name', flat=True))
    
    def get_tags(self):
        """Get all tags associated with this detection."""
        return self.tags.all()
    
    def add_tag(self, tag: 'Tag'):
        """Add a tag to this detection."""
        self.tags.add(tag)

    def remove_tag(self, tag: 'Tag'):
        """Remove a tag from this detection."""
        self.tags.remove(tag)

    def clear_tags(self):
        """Remove all tags from this detection."""
        self.tags.clear()

    def get_tag_names(self):
        """Get a list of tag names associated with this detection."""
        return list(self.tags.values_list('name', flat=True))

class Tag(models.Model):
    # Organization relationship
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='tags',
        help_text=_('Tenant that owns this tag')
    )
    
    name = models.CharField(
        max_length=100,
        help_text=_('Tag name')
    )
    
    description = models.TextField(
        blank=True,
        null=True,
        help_text=_('Tag description')
    )
    
    color = models.CharField(
        max_length=7,
        default='#3B82F6',
        help_text=_('Hex color for UI display')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tag'
        verbose_name = _('Tag')
        verbose_name_plural = _('Tags')
        unique_together = [('tenant', 'name')]
        indexes = [
            models.Index(fields=['tenant', 'name']),
        ]

    def __str__(self):
        return f"{self.name} ({self.tenant.name})"
    
    def save(self, *args, **kwargs):
         """Override save to include validation."""
         if not self.name:
             raise ValidationError({'name': _('Tag name cannot be empty.')})
         super().save(*args, **kwargs)
        
    @property
    def usage_count(self):
        """Get the total count of how many times this tag is used across images, videos, and detections."""
        image_count = self.images.count()   # type: ignore
        video_count = self.videos.count()   # type: ignore
        detection_count = self.detections.count()   # type: ignore
        return {
            'images': image_count,
            'videos': video_count,
            'detections': detection_count,
            'total': image_count + video_count + detection_count
        }
    
    @property
    def usage_examples(self, limit=5):
        """Get example media items that use this tag."""
        image_examples = self.images.all()[:limit]  # type: ignore
        video_examples = self.videos.all()[:limit]  # type: ignore
        detection_examples = self.detections.all()[:limit]  # type: ignore
        return {
            'images': image_examples,
            'videos': video_examples,
            'detections': detection_examples
        }
    
    @property
    def all_media(self):
        """Get all media items (images, videos, detections) associated with this tag."""
        images = self.images.all()    # type: ignore
        videos = self.videos.all()     # type: ignore
        detections = self.detections.all()  # type: ignore
        return {
            'images': images,
            'videos': videos,
            'detections': detections
        }
    

class ImageTag(models.Model):
    image = models.ForeignKey(Image, on_delete=models.CASCADE, related_name='image_tags')
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name='tagged_images')
    tagged_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    tagged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('image', 'tag')
        db_table = 'image_tag'
        verbose_name_plural = 'Image Tags'

    def __str__(self):
        return f"{self.image.filename} - {self.tag.name}"
    
class VideoTag(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='video_tags')
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name='tagged_videos')
    tagged_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    tagged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('video', 'tag')
        db_table = 'video_tag'
        verbose_name_plural = 'Video Tags'

    def __str__(self):
        return f"{self.video.filename} - {self.tag.name}"
    
class DetectionTag(models.Model):
    detection = models.ForeignKey(Detection, on_delete=models.CASCADE, related_name='detection_tags')
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name='tagged_detections')
    tagged_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    tagged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('detection', 'tag')
        db_table = 'detection_tag'
        verbose_name_plural = 'Detection Tags'

    def __str__(self):
        return f"{self.detection.label} - {self.tag.name}"  