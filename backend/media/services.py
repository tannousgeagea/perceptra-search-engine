# apps/media/services.py

from typing import List, Dict, Any, Optional, Tuple
from django.db.models import Q, Count, Sum, Prefetch, QuerySet
from django.core.paginator import Paginator
from tenants.models import Tenant
from media.models import Video, Image, Detection, Tag
from infrastructure.storage.client import get_storage_manager
from datetime import datetime, timedelta
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class MediaLibraryService:
    """Service for media library operations."""
    
    def __init__(self, tenant: Tenant):
        self.tenant = tenant
    
    def _build_video_queryset(self, filters: Dict[str, Any]) -> 'QuerySet':
        """Build filtered queryset for videos."""
        queryset = Video.objects.filter(tenant=self.tenant)
        
        # Search
        if filters.get('search'):
            queryset = queryset.filter(filename__icontains=filters['search'])
        
        # Basic filters
        if filters.get('plant_site'):
            queryset = queryset.filter(plant_site=filters['plant_site'])
        if filters.get('shift'):
            queryset = queryset.filter(shift=filters['shift'])
        if filters.get('inspection_line'):
            queryset = queryset.filter(inspection_line=filters['inspection_line'])
        if filters.get('status'):
            queryset = queryset.filter(status=filters['status'])
        
        # Date range
        if filters.get('date_from'):
            queryset = queryset.filter(recorded_at__gte=filters['date_from'])
        if filters.get('date_to'):
            queryset = queryset.filter(recorded_at__lte=filters['date_to'])
        
        # Duration filters
        if filters.get('min_duration'):
            queryset = queryset.filter(duration_seconds__gte=filters['min_duration'])
        if filters.get('max_duration'):
            queryset = queryset.filter(duration_seconds__lte=filters['max_duration'])
        
        # Has detections
        if filters.get('has_detections') is not None:
            if filters['has_detections']:
                queryset = queryset.filter(frames__detections__isnull=False).distinct()
            else:
                queryset = queryset.filter(frames__detections__isnull=True).distinct()
        
        # Tag filtering
        if filters.get('tags'):
            tag_names = filters['tags']
            if filters.get('tags_match') == 'all':
                # Match all tags
                for tag_name in tag_names:
                    queryset = queryset.filter(tags__name=tag_name)
            else:
                # Match any tag
                queryset = queryset.filter(tags__name__in=tag_names).distinct()
        
        return queryset
    
    def _build_image_queryset(self, filters: Dict[str, Any]) -> 'QuerySet':
        """Build filtered queryset for images."""
        queryset = Image.objects.filter(tenant=self.tenant)
        
        # Search
        if filters.get('search'):
            queryset = queryset.filter(filename__icontains=filters['search'])
        
        # Basic filters
        if filters.get('plant_site'):
            queryset = queryset.filter(plant_site=filters['plant_site'])
        if filters.get('shift'):
            queryset = queryset.filter(shift=filters['shift'])
        if filters.get('inspection_line'):
            queryset = queryset.filter(inspection_line=filters['inspection_line'])
        if filters.get('status'):
            queryset = queryset.filter(status=filters['status'])
        
        # Date range
        if filters.get('date_from'):
            queryset = queryset.filter(captured_at__gte=filters['date_from'])
        if filters.get('date_to'):
            queryset = queryset.filter(captured_at__lte=filters['date_to'])
        
        # Video frame filtering
        if filters.get('is_video_frame') is not None:
            if filters['is_video_frame']:
                queryset = queryset.filter(video__isnull=False)
            else:
                queryset = queryset.filter(video__isnull=True)
        
        if filters.get('video_id'):
            queryset = queryset.filter(video_id=filters['video_id'])
        
        # Has detections
        if filters.get('has_detections') is not None:
            if filters['has_detections']:
                queryset = queryset.filter(detections__isnull=False).distinct()
            else:
                queryset = queryset.filter(detections__isnull=True).distinct()
        
        # Tag filtering
        if filters.get('tags'):
            tag_names = filters['tags']
            if filters.get('tags_match') == 'all':
                for tag_name in tag_names:
                    queryset = queryset.filter(tags__name=tag_name)
            else:
                queryset = queryset.filter(tags__name__in=tag_names).distinct()
        
        return queryset
    
    def _build_detection_queryset(self, filters: Dict[str, Any]) -> 'QuerySet':
        """Build filtered queryset for detections."""
        queryset = Detection.objects.filter(tenant=self.tenant)
        
        # Label filtering
        if filters.get('labels'):
            queryset = queryset.filter(label__in=filters['labels'])
        
        # Confidence range
        if filters.get('min_confidence') is not None:
            queryset = queryset.filter(confidence__gte=filters['min_confidence'])
        if filters.get('max_confidence') is not None:
            queryset = queryset.filter(confidence__lte=filters['max_confidence'])
        
        # Embedding status
        if filters.get('embedding_generated') is not None:
            queryset = queryset.filter(embedding_generated=filters['embedding_generated'])
        
        # Image filters (through relationship)
        if filters.get('plant_site'):
            queryset = queryset.filter(image__plant_site=filters['plant_site'])
        if filters.get('shift'):
            queryset = queryset.filter(image__shift=filters['shift'])
        if filters.get('inspection_line'):
            queryset = queryset.filter(image__inspection_line=filters['inspection_line'])
        
        # Date range (via image)
        if filters.get('date_from'):
            queryset = queryset.filter(image__captured_at__gte=filters['date_from'])
        if filters.get('date_to'):
            queryset = queryset.filter(image__captured_at__lte=filters['date_to'])
        
        # Video filtering (through image)
        if filters.get('video_id'):
            queryset = queryset.filter(image__video_id=filters['video_id'])
        
        # Tag filtering
        if filters.get('tags'):
            tag_names = filters['tags']
            if filters.get('tags_match') == 'all':
                for tag_name in tag_names:
                    queryset = queryset.filter(tags__name=tag_name)
            else:
                queryset = queryset.filter(tags__name__in=tag_names).distinct()
        
        return queryset
    
    def list_videos(
        self,
        filters: Dict[str, Any],
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Video], Dict[str, Any]]:
        """
        List videos with filters and pagination.
        
        Returns:
            Tuple of (video list, pagination metadata)
        """
        # Build queryset
        queryset = self._build_video_queryset(filters)
        
        # Sorting
        sort_by = filters.get('sort_by', 'recorded_at')
        sort_order = filters.get('sort_order', 'desc')
        order_field = f"-{sort_by}" if sort_order == 'desc' else sort_by
        
        queryset = queryset.order_by(order_field)
        
        # Prefetch related data
        queryset = queryset.prefetch_related(
            'tags',
            Prefetch('frames', queryset=Image.objects.all()),
        )
        
        # Pagination
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        
        pagination_metadata = {
            'page': page,
            'page_size': page_size,
            'total_items': paginator.count,
            'total_pages': paginator.num_pages,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous()
        }
        
        return list(page_obj.object_list), pagination_metadata
    
    def list_images(
        self,
        filters: Dict[str, Any],
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Image], Dict[str, Any]]:
        """List images with filters and pagination."""
        # Build queryset
        queryset = self._build_image_queryset(filters)
        
        # Sorting
        sort_by = filters.get('sort_by', 'captured_at')
        sort_order = filters.get('sort_order', 'desc')
        order_field = f"-{sort_by}" if sort_order == 'desc' else sort_by
        
        queryset = queryset.order_by(order_field)
        
        # Prefetch related data
        queryset = queryset.select_related('video').prefetch_related('tags')
        
        # Pagination
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        
        pagination_metadata = {
            'page': page,
            'page_size': page_size,
            'total_items': paginator.count,
            'total_pages': paginator.num_pages,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous()
        }
        
        return list(page_obj.object_list), pagination_metadata
    
    def list_detections(
        self,
        filters: Dict[str, Any],
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Detection], Dict[str, Any]]:
        """List detections with filters and pagination."""
        # Build queryset
        queryset = self._build_detection_queryset(filters)
        
        # Sorting
        sort_by = filters.get('sort_by', 'created_at')
        sort_order = filters.get('sort_order', 'desc')
        order_field = f"-{sort_by}" if sort_order == 'desc' else sort_by
        
        queryset = queryset.order_by(order_field)
        
        # Prefetch related data
        queryset = queryset.select_related('image', 'image__video').prefetch_related('tags')
        
        # Pagination
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        
        pagination_metadata = {
            'page': page,
            'page_size': page_size,
            'total_items': paginator.count,
            'total_pages': paginator.num_pages,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous()
        }
        
        return list(page_obj.object_list), pagination_metadata
    
    def get_media_stats(self) -> Dict[str, Any]:
        """Get media library statistics."""
        from django.db.models import Count, Sum, Q

        # Video stats
        video_stats = Video.objects.filter(tenant=self.tenant).aggregate(
            total=Count('id'),
            total_size=Sum('file_size_bytes')
        )

        videos_by_status = dict(
            Video.objects.filter(tenant=self.tenant)
            .values('status')
            .annotate(count=Count('id'))
            .values_list('status', 'count')
        )

        # Image stats
        image_stats = Image.objects.filter(tenant=self.tenant).aggregate(
            total=Count('id'),
            total_size=Sum('file_size_bytes')
        )

        images_by_status = dict(
            Image.objects.filter(tenant=self.tenant)
            .values('status')
            .annotate(count=Count('id'))
            .values_list('status', 'count')
        )

        # Detection stats
        detection_stats = Detection.objects.filter(tenant=self.tenant).aggregate(
            total=Count('id')
        )

        detections_by_label = list(
            Detection.objects.filter(tenant=self.tenant)
            .values('label')
            .annotate(count=Count('id'))
            .order_by('-count')[:10]
        )

        # Top labels (same data, frontend-friendly key name)
        top_labels = [
            {'label': d['label'], 'count': d['count']}
            for d in detections_by_label
        ]

        # Plant breakdown — images grouped by plant_site with detection counts
        plant_breakdown = list(
            Image.objects.filter(tenant=self.tenant)
            .exclude(plant_site='')
            .values('plant_site')
            .annotate(
                total=Count('id'),
                detections=Count('detections', filter=Q(detections__isnull=False)),
            )
            .order_by('-total')[:10]
        )

        # Recent uploads (last 7 days)
        now = timezone.now()
        seven_days_ago = now - timedelta(days=7)
        fourteen_days_ago = now - timedelta(days=14)

        recent_uploads = {
            'videos': Video.objects.filter(
                tenant=self.tenant,
                created_at__gte=seven_days_ago
            ).count(),
            'images': Image.objects.filter(
                tenant=self.tenant,
                created_at__gte=seven_days_ago
            ).count(),
            'detections': Detection.objects.filter(
                tenant=self.tenant,
                created_at__gte=seven_days_ago
            ).count()
        }

        # Previous period uploads (7-14 days ago) for trend calculation
        previous_uploads = {
            'images': Image.objects.filter(
                tenant=self.tenant,
                created_at__gte=fourteen_days_ago,
                created_at__lt=seven_days_ago,
            ).count(),
            'videos': Video.objects.filter(
                tenant=self.tenant,
                created_at__gte=fourteen_days_ago,
                created_at__lt=seven_days_ago,
            ).count(),
        }

        current_media = recent_uploads['images'] + recent_uploads['videos']
        previous_media = previous_uploads['images'] + previous_uploads['videos']
        media_trend_pct = (
            round((current_media - previous_media) / previous_media * 100)
            if previous_media > 0 else 0
        )

        return {
            'total_videos': video_stats['total'] or 0,
            'total_images': image_stats['total'] or 0,
            'total_detections': detection_stats['total'] or 0,
            'total_storage_bytes': (video_stats['total_size'] or 0) + (image_stats['total_size'] or 0),
            'videos_by_status': videos_by_status,
            'images_by_status': images_by_status,
            'detections_by_label': detections_by_label,
            'top_labels': top_labels,
            'plant_breakdown': plant_breakdown,
            'recent_uploads': recent_uploads,
            'media_trend_pct': media_trend_pct,
        }