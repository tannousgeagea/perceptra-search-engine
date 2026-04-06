# infrastructure/pubsub.py
"""Redis pub/sub wrapper for real-time event broadcasting."""

import os
import json
import logging
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')

# Only use redis pub/sub if broker is redis-based
_USE_REDIS = REDIS_URL.startswith('redis://')


async def publish(channel: str, data: dict) -> None:
    """Publish a JSON message to a Redis pub/sub channel."""
    if not _USE_REDIS:
        logger.debug(f"Redis pub/sub not available, skipping publish to {channel}")
        return

    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(REDIS_URL)
        try:
            await r.publish(channel, json.dumps(data, default=str))
        finally:
            await r.aclose()
    except Exception as e:
        logger.warning(f"Failed to publish to {channel}: {e}")


async def subscribe(channel: str) -> AsyncGenerator[str, None]:
    """Subscribe to a Redis pub/sub channel and yield messages.

    Falls back to a blocking wait if Redis is not available.
    """
    if not _USE_REDIS:
        # Fallback: just block forever (no messages)
        import asyncio
        try:
            while True:
                await asyncio.sleep(30)
                yield json.dumps({"type": "heartbeat"})
        except Exception:
            return

    import redis.asyncio as aioredis
    r = aioredis.from_url(REDIS_URL)
    pubsub = r.pubsub()
    try:
        await pubsub.subscribe(channel)
        async for message in pubsub.listen():
            if message['type'] == 'message':
                yield message['data'].decode() if isinstance(message['data'], bytes) else message['data']
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        await r.aclose()


def publish_sync(channel: str, data: dict) -> None:
    """Synchronous publish for use in Celery tasks."""
    if not _USE_REDIS:
        logger.debug(f"Redis pub/sub not available, skipping sync publish to {channel}")
        return

    try:
        import redis
        r = redis.from_url(REDIS_URL)
        try:
            r.publish(channel, json.dumps(data, default=str))
        finally:
            r.close()
    except Exception as e:
        logger.warning(f"Failed to sync publish to {channel}: {e}")
