__pattern__ = "EventDriven"

import asyncio
import os

import redis.asyncio as aioredis
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.routing import APIRouter

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
            await pubsub.aclose()
        if redis_client:
            await redis_client.aclose()
