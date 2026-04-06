"""
WasteVision frame capture — reads camera streams and emits frames to an asyncio queue.

Supports:
  - RTSP streams (via OpenCV in a thread pool executor)
  - MJPEG HTTP streams (via httpx streaming + multipart parsing)
  - Uploaded video files (via OpenCV in a thread pool executor)
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CapturedFrame:
    camera_id: int          # DB primary key
    camera_uuid: str
    tenant_id: int
    timestamp: datetime
    frame_bytes: bytes       # JPEG-encoded bytes
    sequence_no: int


class CameraStreamManager:
    """
    Manages N concurrent camera stream tasks. Each camera runs as an asyncio.Task
    that reads frames and puts CapturedFrame objects onto a shared queue.
    """

    def __init__(
        self,
        frame_queue: asyncio.Queue,
        max_cameras: int = 16,
    ):
        self._queue = frame_queue
        self._max_cameras = max_cameras
        self._tasks: dict[int, asyncio.Task] = {}   # camera.id → task
        self._seq: dict[int, int] = {}               # camera.id → sequence counter

    async def add_camera(self, camera) -> None:
        """Start streaming a camera. Idempotent — skips if already running."""
        if camera.id in self._tasks:
            return
        if len(self._tasks) >= self._max_cameras:
            logger.warning(
                "WasteVision: max_cameras (%d) reached, cannot add camera %s",
                self._max_cameras, camera.name,
            )
            return
        self._seq[camera.id] = 0
        self._tasks[camera.id] = asyncio.create_task(
            self._stream_camera(camera),
            name=f"wv_camera_{camera.id}",
        )
        logger.info("WasteVision: started stream for camera %s (%s)", camera.name, camera.stream_type)

    async def remove_camera(self, camera_id: int) -> None:
        """Cancel and remove camera stream task."""
        task = self._tasks.pop(camera_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._seq.pop(camera_id, None)

    async def _stream_camera(self, camera) -> None:
        """Dispatch to the correct stream reader based on stream_type."""
        from wastevision.models import CameraStatus
        from asgiref.sync import sync_to_async

        async def set_status(status):
            await sync_to_async(
                type(camera).objects.filter(id=camera.id).update
            )(status=status)

        await set_status(CameraStatus.STREAMING)
        try:
            if camera.stream_type == 'rtsp':
                await self._stream_cv2(camera)
            elif camera.stream_type == 'mjpeg':
                await self._stream_mjpeg(camera)
            elif camera.stream_type == 'upload':
                await self._stream_cv2(camera)
            else:
                logger.error("WasteVision: unknown stream_type '%s' for camera %s", camera.stream_type, camera.name)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("WasteVision: stream error for camera %s: %s", camera.name, e)
            await set_status(CameraStatus.ERROR)

    async def _stream_cv2(self, camera) -> None:
        """Read RTSP / video file via OpenCV in a thread pool executor."""
        import cv2
        from asgiref.sync import sync_to_async

        loop = asyncio.get_event_loop()
        frame_interval = 1.0 / max(camera.target_fps, 0.1)

        def _open_capture():
            cap = cv2.VideoCapture(camera.stream_url)
            return cap

        def _read_frame(cap):
            ret, frame = cap.read()
            return ret, frame

        def _encode_jpeg(frame):
            ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return bytes(buf) if ok else None

        cap = await loop.run_in_executor(None, _open_capture)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open stream: {camera.stream_url}")

        try:
            while True:
                t_start = time.monotonic()

                ret, frame = await loop.run_in_executor(None, _read_frame, cap)
                if not ret:
                    if camera.stream_type == 'upload':
                        logger.info("WasteVision: upload file ended for camera %s", camera.name)
                        break
                    logger.warning("WasteVision: lost frame from camera %s — reconnecting", camera.name)
                    await asyncio.sleep(2.0)
                    cap.release()
                    cap = await loop.run_in_executor(None, _open_capture)
                    continue

                jpeg_bytes = await loop.run_in_executor(None, _encode_jpeg, frame)
                if jpeg_bytes:
                    self._seq[camera.id] = self._seq.get(camera.id, 0) + 1
                    captured = CapturedFrame(
                        camera_id=camera.id,
                        camera_uuid=str(camera.camera_uuid),
                        tenant_id=camera.tenant_id,
                        timestamp=datetime.now(timezone.utc),
                        frame_bytes=jpeg_bytes,
                        sequence_no=self._seq[camera.id],
                    )
                    try:
                        self._queue.put_nowait(captured)
                    except asyncio.QueueFull:
                        logger.warning("WasteVision: frame queue full, dropping frame from camera %s", camera.name)

                elapsed = time.monotonic() - t_start
                sleep_time = frame_interval - elapsed
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
        finally:
            await loop.run_in_executor(None, cap.release)

    async def _stream_mjpeg(self, camera) -> None:
        """Read MJPEG HTTP stream via httpx, parsing multipart/x-mixed-replace boundaries."""
        import httpx

        frame_interval = 1.0 / max(camera.target_fps, 0.1)

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            async with client.stream("GET", camera.stream_url) as response:
                response.raise_for_status()
                buffer = b""
                last_emit = 0.0

                async for chunk in response.aiter_bytes(chunk_size=8192):
                    buffer += chunk

                    # Extract JPEG frames from multipart stream
                    while True:
                        start = buffer.find(b'\xff\xd8')
                        end = buffer.find(b'\xff\xd9', start + 2) if start != -1 else -1
                        if start == -1 or end == -1:
                            break

                        jpeg_bytes = buffer[start:end + 2]
                        buffer = buffer[end + 2:]

                        now = time.monotonic()
                        if now - last_emit < frame_interval:
                            continue
                        last_emit = now

                        self._seq[camera.id] = self._seq.get(camera.id, 0) + 1
                        captured = CapturedFrame(
                            camera_id=camera.id,
                            camera_uuid=str(camera.camera_uuid),
                            tenant_id=camera.tenant_id,
                            timestamp=datetime.now(timezone.utc),
                            frame_bytes=jpeg_bytes,
                            sequence_no=self._seq[camera.id],
                        )
                        try:
                            self._queue.put_nowait(captured)
                        except asyncio.QueueFull:
                            logger.warning(
                                "WasteVision: frame queue full, dropping MJPEG frame from camera %s",
                                camera.name,
                            )
