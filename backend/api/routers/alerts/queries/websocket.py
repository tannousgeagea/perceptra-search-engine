# api/routers/alerts/queries/websocket.py

import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["Alerts WebSocket"])
logger = logging.getLogger(__name__)


async def _authenticate_ws(ws: WebSocket) -> dict | None:
    """Authenticate WebSocket via query param token or API key."""
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
            from django.conf import settings
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
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
            return None
    except Exception as e:
        logger.warning(f"WebSocket auth failed: {e}")
        return None


@router.websocket("/alerts/ws")
async def alert_websocket(ws: WebSocket):
    """WebSocket endpoint for real-time alert notifications.

    Connect with query param: ?token=<jwt_access_token> or ?api_key=<key>
    Receives JSON messages when new alerts are created for the tenant.
    """
    await ws.accept()

    auth_info = await _authenticate_ws(ws)
    if not auth_info:
        await ws.send_json({"error": "Authentication required"})
        await ws.close(code=4001)
        return

    tenant_id = auth_info['tenant_id']
    channel = f"alerts:{tenant_id}"

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
        logger.error(f"WebSocket error for tenant {tenant_id}: {e}")
    finally:
        try:
            await ws.close()
        except Exception:
            pass
