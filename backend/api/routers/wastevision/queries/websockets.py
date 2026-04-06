"""
WasteVision WebSocket endpoints.

  WS /api/v1/wastevision/cameras/{camera_uuid}/stream
    → per-camera live frame result feed
    → subscribes to Redis channel: wastevision:camera:{camera_uuid}

  WS /api/v1/wastevision/alerts/stream
    → global WasteVision alert feed (tenant-scoped)
    → subscribes to Redis channel: wastevision:alerts:{tenant_id}
"""

import json
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["WasteVision WebSocket"])
logger = logging.getLogger(__name__)


async def _authenticate_ws(ws: WebSocket) -> dict | None:
    """Authenticate via ?token=<jwt> or ?api_key=<key> query param."""
    token = ws.query_params.get('token')
    api_key = ws.query_params.get('api_key')

    if not token and not api_key:
        return None

    try:
        if api_key:
            from api_keys.models import ApiKey
            from asgiref.sync import sync_to_async
            key_obj = await sync_to_async(
                ApiKey.objects.select_related('tenant').filter(is_active=True).get
            )(key=api_key)
            return {'tenant_id': key_obj.tenant_id}

        if token:
            import jwt
            from django.conf import settings as djsettings
            payload = jwt.decode(token, djsettings.SECRET_KEY, algorithms=['HS256'])
            if payload.get('token_type') != 'access':
                return None
            user_id = payload.get('user_id')
            if not user_id:
                return None

            from django.contrib.auth import get_user_model
            from tenants.models import TenantMembership
            from asgiref.sync import sync_to_async
            User = get_user_model()
            user = await sync_to_async(User.objects.get)(id=user_id)
            membership = await sync_to_async(
                TenantMembership.objects.filter(user=user, is_active=True).first
            )()
            if membership:
                return {'tenant_id': membership.tenant_id}
    except Exception as e:
        logger.warning("WasteVision WebSocket auth failed: %s", e)

    return None


@router.websocket("/wastevision/cameras/{camera_uuid}/stream")
async def camera_stream_ws(ws: WebSocket, camera_uuid: UUID):
    """
    Live per-camera frame result stream.

    Connect: WS /api/v1/wastevision/cameras/{camera_uuid}/stream?token=<jwt>
    Receives: { type: "frame_result", inspection: WasteInspectionResponse }
    """
    await ws.accept()

    auth_info = await _authenticate_ws(ws)
    if not auth_info:
        await ws.send_json({"error": "Authentication required"})
        await ws.close(code=4001)
        return

    channel = f"wastevision:camera:{camera_uuid}"

    try:
        from infrastructure.pubsub import subscribe
        async for message in subscribe(channel):
            try:
                await ws.send_text(message)
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WasteVision camera WS error (camera=%s): %s", camera_uuid, e)
    finally:
        try:
            await ws.close()
        except Exception:
            pass


@router.websocket("/wastevision/alerts/stream")
async def waste_alerts_ws(ws: WebSocket):
    """
    Global WasteVision alert feed (tenant-scoped).

    Connect: WS /api/v1/wastevision/alerts/stream?token=<jwt>
    Receives: { type: "new_alert", alert: WasteAlertResponse }
    """
    await ws.accept()

    auth_info = await _authenticate_ws(ws)
    if not auth_info:
        await ws.send_json({"error": "Authentication required"})
        await ws.close(code=4001)
        return

    tenant_id = auth_info['tenant_id']
    channel = f"wastevision:alerts:{tenant_id}"

    try:
        from infrastructure.pubsub import subscribe
        async for message in subscribe(channel):
            try:
                await ws.send_text(message)
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WasteVision alerts WS error (tenant=%s): %s", tenant_id, e)
    finally:
        try:
            await ws.close()
        except Exception:
            pass
