"""
WasteVision VLM service — worker pool that consumes frames from the capture queue,
calls the VLM, saves inspection results, and delegates to the alert engine.
"""

import asyncio
import base64
import json
import logging
import os
import re
import time
from datetime import datetime, timezone

from asgiref.sync import sync_to_async
from django.conf import settings

from infrastructure.llm.base import BaseLLMClient
from infrastructure.pubsub import publish
from wastevision.frame_capture import CapturedFrame

logger = logging.getLogger(__name__)


WASTEVISION_SYSTEM_PROMPT = """You are an automated waste inspection AI running 24/7 at a waste \
management facility. Analyze each camera frame and return ONLY valid JSON — no markdown, no preamble.

Return this exact schema:
{
  "waste_composition": {
    "plastic": <0-100>,
    "paper": <0-100>,
    "glass": <0-100>,
    "metal": <0-100>,
    "organic": <0-100>,
    "e_waste": <0-100>,
    "hazardous": <0-100>,
    "other": <0-100>
  },
  "contamination_alerts": [
    {
      "item": "<object name>",
      "severity": "low|medium|high|critical",
      "location_in_frame": "<top-left|top-right|center|bottom-left|bottom-right>",
      "action": "<recommended immediate action>"
    }
  ],
  "line_blockage": <true|false>,
  "overall_risk": "low|medium|high|critical",
  "confidence": <0.0-1.0>,
  "inspector_note": "<one sentence plain-language summary>"
}

Trigger contamination alerts for any hazardous or dangerous material detected.
Always return valid JSON only — never wrap in markdown code blocks."""

_REQUIRED_KEYS = {'waste_composition', 'contamination_alerts', 'line_blockage', 'overall_risk', 'confidence', 'inspector_note'}
_COMPOSITION_KEYS = {'plastic', 'paper', 'glass', 'metal', 'organic', 'e_waste', 'hazardous', 'other'}
_RISK_LEVELS = {'low', 'medium', 'high', 'critical'}


def _build_vlm_client() -> BaseLLMClient:
    """Build a VLM client using WasteVision-specific env vars, falling back to the shared LLM client."""
    provider = settings.WASTEVISION_VLM_PROVIDER or os.environ.get('LLM_PROVIDER', 'anthropic')
    model = settings.WASTEVISION_VLM_MODEL or os.environ.get('LLM_MODEL', '')
    provider = provider.lower()

    if provider == 'anthropic':
        from infrastructure.llm.anthropic_client import AnthropicLLMClient
        return AnthropicLLMClient(
            api_key=os.environ['ANTHROPIC_API_KEY'],
            model=model or 'claude-sonnet-4-20250514',
        )
    elif provider == 'openai':
        from infrastructure.llm.openai_client import OpenAILLMClient
        return OpenAILLMClient(
            api_key=os.environ['OPENAI_API_KEY'],
            model=model or 'gpt-4o',
        )
    elif provider == 'ollama':
        from infrastructure.llm.ollama_client import OllamaLLMClient
        return OllamaLLMClient(
            base_url=os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434'),
            model=model or 'llava',
        )
    raise ValueError(f"Unknown VLM provider: '{provider}'")


def _parse_vlm_response(raw: str) -> dict:
    """Strip markdown fences, parse JSON, validate required keys."""
    # Strip ```json ... ``` or ``` ... ``` wrappers
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*```$', '', cleaned.strip())

    data = json.loads(cleaned)

    missing = _REQUIRED_KEYS - set(data.keys())
    if missing:
        raise ValueError(f"VLM response missing keys: {missing}")

    # Ensure composition has all keys (default 0 for missing)
    comp = data.get('waste_composition', {})
    for k in _COMPOSITION_KEYS:
        comp.setdefault(k, 0.0)
    data['waste_composition'] = comp

    # Normalize risk level
    risk = str(data.get('overall_risk', 'low')).lower()
    if risk not in _RISK_LEVELS:
        risk = 'low'
    data['overall_risk'] = risk

    # Clamp confidence
    data['confidence'] = max(0.0, min(1.0, float(data.get('confidence', 0.0))))

    return data


class WasteVisionService:
    """
    Pulls CapturedFrames from the queue, calls the VLM, saves WasteInspection records,
    publishes results to Redis, and triggers the alert engine.
    """

    def __init__(self, frame_queue: asyncio.Queue):
        self._queue = frame_queue
        self._semaphore = asyncio.Semaphore(settings.WASTEVISION_VLM_WORKERS)
        self._llm: BaseLLMClient | None = None
        self._alert_engine = None

    def _get_llm(self) -> BaseLLMClient:
        if self._llm is None:
            self._llm = _build_vlm_client()
        return self._llm

    def _get_alert_engine(self):
        if self._alert_engine is None:
            from wastevision.alert_engine import AlertEngine
            self._alert_engine = AlertEngine()
        return self._alert_engine

    async def run_workers(self) -> None:
        """Infinite loop: consume frames from queue and dispatch processing tasks."""
        logger.info("WasteVision: VLM worker pool started (%d workers)", settings.WASTEVISION_VLM_WORKERS)
        while True:
            try:
                frame: CapturedFrame = await self._queue.get()
                asyncio.create_task(self._process_frame(frame))
            except asyncio.CancelledError:
                logger.info("WasteVision: VLM worker pool shutting down")
                raise
            except Exception as e:
                logger.error("WasteVision: worker loop error: %s", e)

    async def _process_frame(self, frame: CapturedFrame) -> None:
        async with self._semaphore:
            await self._analyze_with_backoff(frame)

    async def _analyze_with_backoff(self, frame: CapturedFrame, max_retries: int = 4) -> None:
        image_b64 = base64.b64encode(frame.frame_bytes).decode()
        for attempt in range(max_retries):
            try:
                t0 = time.monotonic()
                raw = await self._get_llm().analyze_image(
                    image_b64=image_b64,
                    prompt='Analyze this waste facility frame. Return JSON only.',
                    system_prompt=WASTEVISION_SYSTEM_PROMPT,
                    max_tokens=1024,
                )
                processing_ms = int((time.monotonic() - t0) * 1000)

                data = _parse_vlm_response(raw)
                inspection = await self._save_inspection(frame, data, processing_ms)
                await self._publish_frame_result(frame, inspection)
                await self._get_alert_engine().process(frame, inspection)
                return

            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(
                        "WasteVision: VLM failed after %d retries for camera %s: %s",
                        max_retries, frame.camera_uuid, e,
                    )
                    return
                wait = 2 ** attempt
                logger.warning(
                    "WasteVision: VLM error (attempt %d/%d) for camera %s, retrying in %ds: %s",
                    attempt + 1, max_retries, frame.camera_uuid, wait, e,
                )
                await asyncio.sleep(wait)

    async def _save_inspection(self, frame: CapturedFrame, data: dict, processing_ms: int):
        from wastevision.models import WasteCamera, WasteInspection
        from tenants.models import Tenant

        llm = self._get_llm()
        provider = settings.WASTEVISION_VLM_PROVIDER or os.environ.get('LLM_PROVIDER', 'anthropic')
        model = getattr(llm, '_model', 'unknown')
        tenant = await sync_to_async(Tenant.objects.get)(id=frame.tenant_id)

        def _create():
            return WasteInspection.objects.create(
                tenant=tenant,
                camera_id=frame.camera_id,
                sequence_no=frame.sequence_no,
                frame_timestamp=frame.timestamp,
                waste_composition=data['waste_composition'],
                contamination_alerts=data['contamination_alerts'],
                line_blockage=bool(data['line_blockage']),
                overall_risk=data['overall_risk'],
                confidence=data['confidence'],
                inspector_note=data.get('inspector_note', ''),
                vlm_provider=provider,
                vlm_model=model,
                processing_time_ms=processing_ms,
            )

        inspection = await sync_to_async(_create)()

        # Update camera last_frame_at and last_risk_level
        await sync_to_async(
            WasteCamera.objects.filter(id=frame.camera_id).update
        )(
            last_frame_at=frame.timestamp,
            last_risk_level=data['overall_risk'],
        )

        return inspection

    async def _publish_frame_result(self, frame: CapturedFrame, inspection) -> None:
        """Publish inspection result to per-camera Redis channel."""
        channel = f"wastevision:camera:{frame.camera_uuid}"
        msg = {
            "type": "frame_result",
            "inspection": {
                "inspection_uuid": str(inspection.inspection_uuid),
                "camera_uuid": frame.camera_uuid,
                "sequence_no": inspection.sequence_no,
                "frame_timestamp": inspection.frame_timestamp.isoformat(),
                "waste_composition": inspection.waste_composition,
                "contamination_alerts": inspection.contamination_alerts,
                "line_blockage": inspection.line_blockage,
                "overall_risk": inspection.overall_risk,
                "confidence": inspection.confidence,
                "inspector_note": inspection.inspector_note,
                "vlm_provider": inspection.vlm_provider,
                "vlm_model": inspection.vlm_model,
                "processing_time_ms": inspection.processing_time_ms,
                "created_at": inspection.created_at.isoformat(),
            },
        }
        await publish(channel, msg)

    async def analyze_frame_sync(self, camera_uuid: str, image_b64: str, tenant_id: int):
        """
        Synchronous (request-response) frame analysis for the REST endpoint.
        Returns the WasteInspection ORM object.
        """
        from wastevision.models import WasteCamera
        from tenants.models import Tenant

        camera = await sync_to_async(WasteCamera.objects.get)(camera_uuid=camera_uuid)
        seq = await sync_to_async(
            lambda: WasteInspection_count(camera)
        )()

        frame = CapturedFrame(
            camera_id=camera.id,
            camera_uuid=str(camera.camera_uuid),
            tenant_id=tenant_id,
            timestamp=datetime.now(timezone.utc),
            frame_bytes=base64.b64decode(image_b64),
            sequence_no=seq + 1,
        )

        # Run VLM directly (no queue)
        t0 = time.monotonic()
        raw = await self._get_llm().analyze_image(
            image_b64=image_b64,
            prompt='Analyze this waste facility frame. Return JSON only.',
            system_prompt=WASTEVISION_SYSTEM_PROMPT,
            max_tokens=1024,
        )
        processing_ms = int((time.monotonic() - t0) * 1000)

        data = _parse_vlm_response(raw)
        inspection = await self._save_inspection(frame, data, processing_ms)
        await self._publish_frame_result(frame, inspection)
        await self._get_alert_engine().process(frame, inspection)
        return inspection


def WasteInspection_count(camera) -> int:
    from wastevision.models import WasteInspection
    return WasteInspection.objects.filter(camera=camera).count()
