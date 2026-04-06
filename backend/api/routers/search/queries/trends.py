# api/routers/search/queries/trends.py
"""Defect trend analytics and anomaly detection endpoints."""

import math
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from asgiref.sync import sync_to_async
from pydantic import BaseModel
from django.db.models import Count
from django.db.models.functions import TruncDate, TruncWeek
from django.utils import timezone

from tenants.context import RequestContext
from api.dependencies import require_permission
from media.models import Detection

router = APIRouter(prefix="/search", tags=["Trends & Anomalies"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TrendPoint(BaseModel):
    date: str
    count: int


class TrendSeries(BaseModel):
    label: str
    data: List[TrendPoint]


class TrendResponse(BaseModel):
    series: List[TrendSeries]
    granularity: str
    days: int


class AnomalyItem(BaseModel):
    label: str
    plant_site: Optional[str]
    current_count: int
    avg_count: float
    z_score: float
    pct_change: float
    severity: str
    period: str


class AnomalyResponse(BaseModel):
    anomalies: List[AnomalyItem]
    checked_at: datetime


class HeatmapCell(BaseModel):
    label: str
    plant_site: str
    count: int


class HeatmapResponse(BaseModel):
    cells: List[HeatmapCell]
    labels: List[str]
    plant_sites: List[str]


# ---------------------------------------------------------------------------
# Trend endpoint
# ---------------------------------------------------------------------------

@router.get("/stats/trends", response_model=TrendResponse)
async def get_detection_trends(
    ctx: RequestContext = Depends(require_permission('read')),
    labels: Optional[str] = Query(default=None, description="Comma-separated label names"),
    plant_site: Optional[str] = None,
    granularity: str = Query(default='day', pattern='^(day|week)$'),
    days: int = Query(default=90, ge=7, le=365),
):
    """Time-series data of detection counts by label."""
    cutoff = timezone.now() - timedelta(days=days)

    def _query():
        qs = Detection.objects.filter(tenant=ctx.tenant, created_at__gte=cutoff)
        if labels:
            label_list = [l.strip() for l in labels.split(',') if l.strip()]
            if label_list:
                qs = qs.filter(label__in=label_list)
        if plant_site:
            qs = qs.filter(image__plant_site=plant_site)

        trunc_fn = TruncDate('created_at') if granularity == 'day' else TruncWeek('created_at')
        rows = (
            qs.annotate(period=trunc_fn)
            .values('label', 'period')
            .annotate(count=Count('id'))
            .order_by('period')
        )

        # Group by label
        series_map: dict[str, list[TrendPoint]] = {}
        for row in rows:
            label = row['label']
            if label not in series_map:
                series_map[label] = []
            series_map[label].append(TrendPoint(
                date=str(row['period']),
                count=row['count'],
            ))

        return [TrendSeries(label=k, data=v) for k, v in series_map.items()]

    series = await sync_to_async(_query)()
    return TrendResponse(series=series, granularity=granularity, days=days)


# ---------------------------------------------------------------------------
# Anomaly endpoint
# ---------------------------------------------------------------------------

@router.get("/stats/anomalies", response_model=AnomalyResponse)
async def get_anomalies(
    ctx: RequestContext = Depends(require_permission('read')),
    window: int = Query(default=30, ge=7, le=90, description="Rolling window in days"),
    threshold: float = Query(default=2.0, ge=1.0, le=5.0, description="Z-score threshold"),
):
    """Detect anomalous spikes in defect rates using Z-score analysis."""
    now = timezone.now()
    cutoff = now - timedelta(days=window + 7)  # Extra week for context

    def _detect():
        qs = Detection.objects.filter(tenant=ctx.tenant, created_at__gte=cutoff)
        rows = list(
            qs.annotate(period=TruncDate('created_at'))
            .values('label', 'image__plant_site', 'period')
            .annotate(count=Count('id'))
            .order_by('period')
        )

        # Group by (label, plant_site)
        groups: dict[tuple[str, str | None], list[tuple[str, int]]] = {}
        for row in rows:
            key = (row['label'], row['image__plant_site'])
            if key not in groups:
                groups[key] = []
            groups[key].append((str(row['period']), row['count']))

        anomalies = []
        recent_cutoff = str((now - timedelta(days=7)).date())

        for (label, plant), datapoints in groups.items():
            if len(datapoints) < 5:
                continue

            counts = [c for _, c in datapoints]
            recent_counts = [c for d, c in datapoints if d >= recent_cutoff]

            if not recent_counts:
                continue

            # Rolling stats over the full window
            mean_val = sum(counts) / len(counts)
            if mean_val == 0:
                continue
            variance = sum((c - mean_val) ** 2 for c in counts) / len(counts)
            std_val = math.sqrt(variance) if variance > 0 else 0.001

            # Current period = sum of recent week
            current = sum(recent_counts)
            expected = mean_val * len(recent_counts)
            if expected == 0:
                continue

            z = (current - expected) / (std_val * math.sqrt(len(recent_counts))) if std_val > 0.001 else 0
            pct_change = ((current - expected) / expected) * 100

            if z >= threshold:
                severity = 'critical' if z >= 3.0 else 'warning'
                anomalies.append(AnomalyItem(
                    label=label,
                    plant_site=plant,
                    current_count=current,
                    avg_count=round(expected, 1),
                    z_score=round(z, 2),
                    pct_change=round(pct_change, 1),
                    severity=severity,
                    period=f"Last 7 days vs {window}-day average",
                ))

        anomalies.sort(key=lambda a: a.z_score, reverse=True)
        return anomalies

    anomalies = await sync_to_async(_detect)()
    return AnomalyResponse(anomalies=anomalies, checked_at=now)


# ---------------------------------------------------------------------------
# Heatmap endpoint
# ---------------------------------------------------------------------------

@router.get("/stats/heatmap", response_model=HeatmapResponse)
async def get_heatmap(
    ctx: RequestContext = Depends(require_permission('read')),
    days: int = Query(default=30, ge=7, le=365),
):
    """Label x Plant matrix of detection counts."""
    cutoff = timezone.now() - timedelta(days=days)

    def _query():
        qs = Detection.objects.filter(tenant=ctx.tenant, created_at__gte=cutoff)
        rows = list(
            qs.values('label', 'image__plant_site')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        cells = []
        labels_set: set[str] = set()
        plants_set: set[str] = set()
        for row in rows:
            label = row['label']
            plant = row['image__plant_site'] or 'Unknown'
            labels_set.add(label)
            plants_set.add(plant)
            cells.append(HeatmapCell(label=label, plant_site=plant, count=row['count']))

        return cells, sorted(labels_set), sorted(plants_set)

    cells, labels, plants = await sync_to_async(_query)()
    return HeatmapResponse(cells=cells, labels=labels, plant_sites=plants)
