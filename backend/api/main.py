import asyncio
import os
import uvicorn
import logging
import inspect
import importlib
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi import HTTPException, Body, status, Request
import sys
from pathlib import Path
base_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(base_dir))



ROUTERS_DIR = os.path.dirname(__file__) + "/routers"
ROUTERS = [
    f"api.routers.{f.replace('/', '.')}" 
    for f in os.listdir(ROUTERS_DIR)
    if not f.endswith('__pycache__')
    if not f.endswith('__.py')
    ]

@asynccontextmanager
async def _wastevision_lifespan(app: FastAPI):
    """Boot WasteVision stream manager and VLM worker pool on startup."""
    try:
        from django.conf import settings as djsettings
        from asgiref.sync import sync_to_async
        from wastevision.frame_capture import CameraStreamManager
        from wastevision.service import WasteVisionService

        frame_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        stream_manager = CameraStreamManager(
            frame_queue,
            max_cameras=djsettings.WASTEVISION_MAX_CAMERAS,
        )
        vlm_service = WasteVisionService(frame_queue)

        app.state.wv_frame_queue = frame_queue
        app.state.wv_stream_manager = stream_manager
        app.state.wv_vlm_service = vlm_service

        # Start all active cameras
        from wastevision.models import WasteCamera
        active_cams = await sync_to_async(list)(
            WasteCamera.objects.filter(is_active=True).select_related('tenant')
        )
        for cam in active_cams:
            await stream_manager.add_camera(cam)

        worker_task = asyncio.create_task(vlm_service.run_workers(), name="wv_vlm_workers")
        logging.getLogger(__name__).info(
            "WasteVision: lifespan started — %d active cameras", len(active_cams)
        )
    except Exception as e:
        logging.getLogger(__name__).warning("WasteVision: lifespan init failed (non-fatal): %s", e)
        worker_task = None

    yield

    if worker_task:
        worker_task.cancel()
        try:
            await asyncio.gather(worker_task, return_exceptions=True)
        except Exception:
            pass
    logging.getLogger(__name__).info("WasteVision: lifespan shutdown complete")


def create_app() -> FastAPI:

    import django
    django.setup()
    
    tags_meta = [
        {
            "name": "Search Engine API",
            "description": "Multi-modal search for industrial inspection data"
        }
    ]

    app = FastAPI(
        openapi_tags=tags_meta,
        debug=True,
        title="Search Engine API",
        summary="",
        version="0.0.1",
        contact={
            "name": "Tannous Geagea",
            "url": "https://wasteant.com",
            "email": "tannous.geagea@wasteant.com",
        },
        openapi_url="/openapi.json",
        lifespan=_wastevision_lifespan,
    )

    origins = ["http://localhost:3000", os.getenv("FRONTEND_ENDPOINT")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["X-Requested-With", "X-Request-ID", "X-Organization-ID", "Authorization", "X-API-Key", "X-Tenant-ID", "X-Tenant-Domain"],
        expose_headers=["X-Request-ID", "X-Progress-ID", "x-response-time"],
    )

    for R in ROUTERS:
        try:
            module = importlib.import_module(R)
            attr = getattr(module, 'endpoint')
            if inspect.ismodule(attr):
                app.include_router(module.endpoint.router)
        except ImportError as err:
            logging.error(f'Failed to import {R}: {err}')
    
    return app

app = create_app()

@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/")
async def root():
    return {"message": "Impurity Search Engine API"}

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status_code": exc.status_code,
            "status_description": exc.detail,
            "detail": exc.detail
        }
    )

@app.exception_handler(Exception)
async def internal_server_error_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "status_code": 500,
            "status_description": "Internal Server Error",
            "detail": "An unexpected error occurred. Please try again later."
        }
    )

if __name__ == "__main__":
    import os
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv('SEARCH_ENGINE_PORT', 8000)), log_level="debug", reload=True)