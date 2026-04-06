# api/routers/exports/queries/exports.py
"""Export media, detections, and analytics as CSV/JSON."""

import csv
import io
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from asgiref.sync import sync_to_async
from pydantic import BaseModel

from tenants.context import RequestContext
from api.dependencies import require_permission
from media.models import Image, Detection

router = APIRouter(prefix="/exports", tags=["Exports"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stream_csv(rows, headers, filename):
    """Generate a streaming CSV response."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


def _stream_json(data, filename):
    """Generate a streaming JSON response."""
    content = json.dumps(data, default=str, indent=2)
    return StreamingResponse(
        iter([content]),
        media_type='application/json',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/media")
async def export_media(
    ctx: RequestContext = Depends(require_permission('read')),
    format: str = Query(default='csv', pattern='^(csv|json)$'),
    plant_site: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Export media metadata as CSV or JSON."""
    def _query():
        qs = Image.objects.filter(tenant=ctx.tenant).order_by('-created_at')
        if plant_site:
            qs = qs.filter(plant_site=plant_site)
        if date_from:
            qs = qs.filter(captured_at__gte=date_from)
        if date_to:
            qs = qs.filter(captured_at__lte=date_to)

        return list(qs.values(
            'id', 'image_id', 'filename', 'plant_site', 'shift',
            'inspection_line', 'captured_at', 'width', 'height',
            'status', 'detection_count', 'created_at',
        )[:5000])

    rows = await sync_to_async(_query)()
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')

    if format == 'json':
        return _stream_json(rows, f'media_export_{ts}.json')

    headers = ['id', 'image_id', 'filename', 'plant_site', 'shift',
               'inspection_line', 'captured_at', 'width', 'height',
               'status', 'detection_count', 'created_at']
    csv_rows = [[r.get(h, '') for h in headers] for r in rows]
    return _stream_csv(csv_rows, headers, f'media_export_{ts}.csv')


@router.post("/detections")
async def export_detections(
    ctx: RequestContext = Depends(require_permission('read')),
    format: str = Query(default='csv', pattern='^(csv|json)$'),
    label: Optional[str] = None,
    plant_site: Optional[str] = None,
    min_confidence: Optional[float] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Export detection data as CSV or JSON."""
    def _query():
        qs = Detection.objects.filter(tenant=ctx.tenant).select_related('image').order_by('-created_at')
        if label:
            qs = qs.filter(label=label)
        if plant_site:
            qs = qs.filter(image__plant_site=plant_site)
        if min_confidence:
            qs = qs.filter(confidence__gte=min_confidence)
        if date_from:
            qs = qs.filter(created_at__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__lte=date_to)

        results = []
        for d in qs[:5000]:
            results.append({
                'id': d.pk,
                'detection_id': str(d.detection_id),
                'label': d.label,
                'confidence': d.confidence,
                'bbox_x': d.bbox_x,
                'bbox_y': d.bbox_y,
                'bbox_width': d.bbox_width,
                'bbox_height': d.bbox_height,
                'image_id': d.image_id,
                'image_filename': d.image.filename if d.image else '',
                'plant_site': d.image.plant_site if d.image else '',
                'shift': d.image.shift if d.image else '',
                'source': d.source,
                'created_at': str(d.created_at),
            })
        return results

    rows = await sync_to_async(_query)()
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')

    if format == 'json':
        return _stream_json(rows, f'detections_export_{ts}.json')

    headers = ['id', 'detection_id', 'label', 'confidence', 'bbox_x', 'bbox_y',
               'bbox_width', 'bbox_height', 'image_id', 'image_filename',
               'plant_site', 'shift', 'source', 'created_at']
    csv_rows = [[r.get(h, '') for h in headers] for r in rows]
    return _stream_csv(csv_rows, headers, f'detections_export_{ts}.csv')


@router.post("/analytics")
async def export_analytics(
    ctx: RequestContext = Depends(require_permission('read')),
    days: int = Query(default=30, ge=7, le=365),
):
    """Export analytics summary as JSON."""
    from django.db.models import Count
    from django.db.models.functions import TruncDate

    cutoff = datetime.utcnow() - timedelta(days=days)

    def _build():
        images = Image.objects.filter(tenant=ctx.tenant, created_at__gte=cutoff)
        detections = Detection.objects.filter(tenant=ctx.tenant, created_at__gte=cutoff)

        by_label = list(
            detections.values('label').annotate(count=Count('id')).order_by('-count')[:20]
        )
        by_plant = list(
            images.values('plant_site').annotate(count=Count('id')).order_by('-count')[:20]
        )
        daily = list(
            detections.annotate(date=TruncDate('created_at'))
            .values('date').annotate(count=Count('id')).order_by('date')
        )

        return {
            'period_days': days,
            'total_images': images.count(),
            'total_detections': detections.count(),
            'detections_by_label': by_label,
            'images_by_plant': by_plant,
            'daily_detections': [{'date': str(d['date']), 'count': d['count']} for d in daily],
            'exported_at': str(datetime.utcnow()),
        }

    data = await sync_to_async(_build)()
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    return _stream_json(data, f'analytics_export_{ts}.json')
