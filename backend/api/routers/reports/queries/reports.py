# api/routers/reports/queries/reports.py

import io
import logging
from datetime import datetime, timedelta, time as dtime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from asgiref.sync import sync_to_async
from pydantic import BaseModel
from django.db.models import Count, Q, Avg
from django.utils import timezone as django_tz

from tenants.context import RequestContext
from api.dependencies import require_permission
from media.models import Image, Detection

router = APIRouter(prefix="/reports", tags=["Reports"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ShiftUploads(BaseModel):
    total: int
    images: int
    videos: int


class HighSeverityItem(BaseModel):
    detection_id: int
    label: str
    confidence: float
    image_id: int
    image_filename: str
    crop_url: Optional[str]


class LabelCount(BaseModel):
    label: str
    count: int


class ShiftDetections(BaseModel):
    total: int
    by_label: List[LabelCount]
    high_severity: List[HighSeverityItem]


class ShiftAlerts(BaseModel):
    total: int
    unacknowledged: int
    critical: int


class ShiftComparison(BaseModel):
    prev_uploads: int
    prev_detections: int
    upload_delta_pct: float
    detection_delta_pct: float


class ShiftSummaryResponse(BaseModel):
    shift: str
    date: str
    plant_site: Optional[str]
    period_start: datetime
    period_end: datetime
    uploads: ShiftUploads
    detections: ShiftDetections
    alerts: ShiftAlerts
    comparison: ShiftComparison


class AvailableShift(BaseModel):
    date: str
    shift: str
    image_count: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SHIFT_WINDOWS = {
    'morning':   (dtime(6, 0), dtime(14, 0)),
    'afternoon': (dtime(14, 0), dtime(22, 0)),
    'night':     (dtime(22, 0), dtime(6, 0)),  # crosses midnight
}


def _shift_window(shift: str, date_str: str) -> tuple[datetime, datetime]:
    """Return (start, end) UTC datetimes for a shift on a given date."""
    d = datetime.strptime(date_str, '%Y-%m-%d').date()
    start_t, end_t = SHIFT_WINDOWS.get(shift, SHIFT_WINDOWS['morning'])

    if shift == 'night':
        start = datetime.combine(d, start_t)
        end = datetime.combine(d + timedelta(days=1), end_t)
    else:
        start = datetime.combine(d, start_t)
        end = datetime.combine(d, end_t)

    return start, end


def _prev_shift_date(shift: str, date_str: str) -> str:
    """Return the previous occurrence date for comparison."""
    d = datetime.strptime(date_str, '%Y-%m-%d').date()
    return (d - timedelta(days=1)).isoformat()


def _delta_pct(current: int, previous: int) -> float:
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100, 1)


async def _build_shift_summary(
    shift: str, date_str: str, plant_site: Optional[str], tenant,
) -> ShiftSummaryResponse:
    start, end = _shift_window(shift, date_str)

    # Current shift images
    img_qs = Image.objects.filter(
        tenant=tenant,
        captured_at__gte=start,
        captured_at__lt=end,
    )
    if plant_site:
        img_qs = img_qs.filter(plant_site=plant_site)

    image_count = await sync_to_async(img_qs.count)()

    # Video count (images with video FK)
    video_count = await sync_to_async(
        img_qs.filter(video__isnull=False).values('video_id').distinct().count
    )()

    # Detections in this shift
    det_qs = Detection.objects.filter(
        tenant=tenant,
        image__in=img_qs,
    ).select_related('image')

    det_count = await sync_to_async(det_qs.count)()

    # By label
    by_label_raw = await sync_to_async(list)(
        det_qs.values('label').annotate(count=Count('id')).order_by('-count')[:10]
    )
    by_label = [LabelCount(label=r['label'], count=r['count']) for r in by_label_raw]

    # High severity (confidence > 0.8)
    high_sev_qs = det_qs.filter(confidence__gte=0.8).select_related('image').order_by('-confidence')[:10]
    high_sev_items = await sync_to_async(list)(high_sev_qs)
    high_severity = [
        HighSeverityItem(
            detection_id=d.pk,
            label=d.label,
            confidence=d.confidence,
            image_id=d.image_id,
            image_filename=d.image.filename if d.image else '',
            crop_url=f'/api/v1/media/files/{d.storage_key}' if d.storage_key else None,
        )
        for d in high_sev_items
    ]

    # Alerts for this shift
    alert_total = 0
    alert_unack = 0
    alert_critical = 0
    try:
        from alerts.models import Alert
        alert_qs = Alert.objects.filter(
            tenant=tenant,
            created_at__gte=start,
            created_at__lt=end,
        )
        if plant_site:
            alert_qs = alert_qs.filter(plant_site=plant_site)
        alert_total = await sync_to_async(alert_qs.count)()
        alert_unack = await sync_to_async(alert_qs.filter(is_acknowledged=False).count)()
        alert_critical = await sync_to_async(alert_qs.filter(severity='critical').count)()
    except Exception:
        pass

    # Previous shift comparison
    prev_date = _prev_shift_date(shift, date_str)
    prev_start, prev_end = _shift_window(shift, prev_date)
    prev_img_qs = Image.objects.filter(
        tenant=tenant,
        captured_at__gte=prev_start,
        captured_at__lt=prev_end,
    )
    if plant_site:
        prev_img_qs = prev_img_qs.filter(plant_site=plant_site)

    prev_uploads = await sync_to_async(prev_img_qs.count)()
    prev_det_count = await sync_to_async(
        Detection.objects.filter(tenant=tenant, image__in=prev_img_qs).count
    )()

    return ShiftSummaryResponse(
        shift=shift,
        date=date_str,
        plant_site=plant_site,
        period_start=start,
        period_end=end,
        uploads=ShiftUploads(total=image_count + video_count, images=image_count, videos=video_count),
        detections=ShiftDetections(total=det_count, by_label=by_label, high_severity=high_severity),
        alerts=ShiftAlerts(total=alert_total, unacknowledged=alert_unack, critical=alert_critical),
        comparison=ShiftComparison(
            prev_uploads=prev_uploads,
            prev_detections=prev_det_count,
            upload_delta_pct=_delta_pct(image_count, prev_uploads),
            detection_delta_pct=_delta_pct(det_count, prev_det_count),
        ),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/shift-summary", response_model=ShiftSummaryResponse)
async def get_shift_summary(
    ctx: RequestContext = Depends(require_permission('read')),
    shift: str = Query(default='morning', pattern='^(morning|afternoon|night)$'),
    date: str = Query(default_factory=lambda: django_tz.now().strftime('%Y-%m-%d')),
    plant_site: Optional[str] = None,
):
    """Get shift summary report as JSON."""
    return await _build_shift_summary(shift, date, plant_site, ctx.tenant)


@router.get("/shift-summary/pdf")
async def get_shift_summary_pdf(
    ctx: RequestContext = Depends(require_permission('read')),
    shift: str = Query(default='morning', pattern='^(morning|afternoon|night)$'),
    date: str = Query(default_factory=lambda: django_tz.now().strftime('%Y-%m-%d')),
    plant_site: Optional[str] = None,
):
    """Download shift summary as PDF."""
    summary = await _build_shift_summary(shift, date, plant_site, ctx.tenant)

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="PDF generation requires reportlab. Install with: pip install reportlab",
        )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('Title2', parent=styles['Title'], fontSize=18, spaceAfter=12)
    subtitle_style = ParagraphStyle('Sub', parent=styles['Normal'], fontSize=11, textColor=colors.gray)
    section_style = ParagraphStyle('Section', parent=styles['Heading2'], fontSize=13, spaceBefore=16, spaceAfter=8)

    elements = []

    # Header
    tenant_name = await sync_to_async(lambda: ctx.tenant.name)()
    elements.append(Paragraph(f"Shift Handoff Report — {tenant_name}", title_style))
    elements.append(Paragraph(
        f"Shift: {summary.shift.capitalize()} | Date: {summary.date} | "
        f"Plant: {summary.plant_site or 'All'} | "
        f"Period: {summary.period_start.strftime('%H:%M')} — {summary.period_end.strftime('%H:%M')}",
        subtitle_style,
    ))
    elements.append(Spacer(1, 12))

    # KPI table
    kpi_data = [
        ['Metric', 'This Shift', 'Previous Shift', 'Change'],
        ['Uploads', str(summary.uploads.total), str(summary.comparison.prev_uploads),
         f"{summary.comparison.upload_delta_pct:+.1f}%"],
        ['Detections', str(summary.detections.total), str(summary.comparison.prev_detections),
         f"{summary.comparison.detection_delta_pct:+.1f}%"],
        ['Alerts', str(summary.alerts.total), '—', '—'],
        ['Critical Alerts', str(summary.alerts.critical), '—', '—'],
    ]
    kpi_table = Table(kpi_data, colWidths=[120, 100, 120, 80])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2A2E3B')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#444')),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#F8F9FA'), colors.white]),
    ]))
    elements.append(kpi_table)
    elements.append(Spacer(1, 16))

    # Detections by label
    if summary.detections.by_label:
        elements.append(Paragraph("Detections by Label", section_style))
        label_data = [['Label', 'Count']]
        for lc in summary.detections.by_label:
            label_data.append([lc.label, str(lc.count)])
        label_table = Table(label_data, colWidths=[200, 80])
        label_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2A2E3B')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#444')),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ]))
        elements.append(label_table)
        elements.append(Spacer(1, 12))

    # High severity items
    if summary.detections.high_severity:
        elements.append(Paragraph("High-Severity Detections", section_style))
        hs_data = [['Detection', 'Label', 'Confidence', 'Image']]
        for hs in summary.detections.high_severity:
            hs_data.append([
                str(hs.detection_id), hs.label,
                f"{hs.confidence:.1%}", hs.image_filename,
            ])
        hs_table = Table(hs_data, colWidths=[80, 120, 80, 160])
        hs_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7F1D1D')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#444')),
            ('ALIGN', (2, 0), (2, -1), 'CENTER'),
        ]))
        elements.append(hs_table)

    # Footer
    elements.append(Spacer(1, 24))
    elements.append(Paragraph(
        f"Generated {django_tz.now().strftime('%Y-%m-%d %H:%M UTC')} — OptiVyn",
        ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.gray),
    ))

    doc.build(elements)
    buf.seek(0)

    filename = f"shift_report_{summary.shift}_{summary.date}.pdf"
    return StreamingResponse(
        buf,
        media_type='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@router.get("/available-shifts", response_model=List[AvailableShift])
async def get_available_shifts(
    ctx: RequestContext = Depends(require_permission('read')),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """List shifts that have data for a date range."""
    qs = Image.objects.filter(tenant=ctx.tenant)

    if not date_from:
        date_from = (django_tz.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    if not date_to:
        date_to = django_tz.now().strftime('%Y-%m-%d')

    qs = qs.filter(captured_at__date__gte=date_from, captured_at__date__lte=date_to)

    def _get_shifts():
        results = []
        from django.db.models.functions import TruncDate, ExtractHour
        # Group images by date and determine shift from hour
        rows = (
            qs.annotate(
                img_date=TruncDate('captured_at'),
                img_hour=ExtractHour('captured_at'),
            )
            .values('img_date', 'img_hour')
            .annotate(count=Count('id'))
            .order_by('-img_date')
        )
        # Aggregate into shift buckets
        shift_map: dict[tuple, int] = {}
        for row in rows:
            d = row['img_date']
            h = row['img_hour']
            if 6 <= h < 14:
                s = 'morning'
            elif 14 <= h < 22:
                s = 'afternoon'
            else:
                s = 'night'
            key = (str(d), s)
            shift_map[key] = shift_map.get(key, 0) + row['count']

        for (date_str, shift), count in sorted(shift_map.items(), reverse=True):
            results.append(AvailableShift(date=date_str, shift=shift, image_count=count))
        return results

    return await sync_to_async(_get_shifts)()
