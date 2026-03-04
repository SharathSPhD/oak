__pattern__ = "EventDriven"

import asyncio
import os

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.routing import APIRouter

try:
    import redis.asyncio as aioredis  # available at runtime inside Docker
except ImportError:  # pragma: no cover — redis absent only in bare test envs
    aioredis = None  # type: ignore[assignment]

router = APIRouter()

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")


@router.websocket("/ws/{problem_uuid}")
async def websocket_stream(websocket: WebSocket, problem_uuid: str) -> None:
    """Stream agent events to Hub via WebSocket. Subscribes to oak:stream:{problem_uuid}."""
    await websocket.accept()
    redis_client = None
    pubsub = None
    try:
        redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
        pubsub = redis_client.pubsub()
        channel = f"oak:stream:{problem_uuid}"
        await pubsub.subscribe(channel)
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                await websocket.send_text(message["data"])
            else:
                # Send heartbeat to keep connection alive
                await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    finally:
        if pubsub:
            await pubsub.unsubscribe()
            await pubsub.aclose()  # type: ignore[no-untyped-call]
        if redis_client:
            await redis_client.aclose()
