"""Builder observability endpoints.

Provides status, history, and manual control for the self-build service.
The builder itself runs in a separate container; these endpoints read/write
shared state via Redis to communicate with it.
"""
__pattern__ = "Observer"

import json
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException

from api.config import settings

router = APIRouter(prefix="/api/builder", tags=["builder"])

REDIS_STATE_KEY = "oak:builder:state"
REDIS_HISTORY_KEY = "oak:builder:history"
REDIS_CONTROL_KEY = "oak:builder:control"


async def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


@router.get("/status")
async def builder_status() -> dict[str, Any]:
    """Current builder status: sprint state, circuit breaker, progress."""
    r = await _get_redis()
    try:
        raw = await r.get(REDIS_STATE_KEY)
        if raw:
            return json.loads(raw)
        return {
            "status": "idle",
            "builder_enabled": settings.builder_enabled,
            "circuit_breaker": {"state": "closed", "consecutive_failures": 0},
            "current_sprint": None,
            "last_sprint_result": None,
        }
    finally:
        await r.aclose()


@router.post("/start-sprint")
async def start_sprint() -> dict[str, str]:
    """Trigger a sprint manually (also called by the daemon)."""
    if not settings.builder_enabled:
        raise HTTPException(status_code=403, detail="Builder is disabled")

    r = await _get_redis()
    try:
        await r.publish("oak:builder:control", json.dumps({"action": "start"}))
        await r.set(
            REDIS_CONTROL_KEY,
            json.dumps({"action": "start"}),
            ex=60,
        )
        return {"status": "sprint_triggered"}
    finally:
        await r.aclose()


@router.post("/pause")
async def pause_builder() -> dict[str, str]:
    """Pause the builder (manual control)."""
    r = await _get_redis()
    try:
        await r.publish("oak:builder:control", json.dumps({"action": "pause"}))
        return {"status": "pause_requested"}
    finally:
        await r.aclose()


@router.post("/resume")
async def resume_builder() -> dict[str, str]:
    """Resume the builder and reset circuit breaker if halted."""
    r = await _get_redis()
    try:
        await r.publish("oak:builder:control", json.dumps({"action": "resume"}))
        return {"status": "resume_requested"}
    finally:
        await r.aclose()


@router.get("/heartbeat")
async def builder_heartbeat() -> dict[str, Any]:
    """Heartbeat endpoint for the watchdog to verify builder health."""
    r = await _get_redis()
    try:
        raw = await r.get(REDIS_STATE_KEY)
        state = json.loads(raw) if raw else {"status": "idle"}
        return {
            "alive": True,
            "status": state.get("status", "unknown"),
            "cycle_count": state.get("cycle_count", 0),
        }
    finally:
        await r.aclose()


@router.get("/history")
async def builder_history(limit: int = 10) -> dict[str, Any]:
    """Past sprint results with per-domain skill counts."""
    r = await _get_redis()
    try:
        raw = await r.get(REDIS_HISTORY_KEY)
        if raw:
            data = json.loads(raw)
            sprints = data.get("sprints", [])
            return {
                "sprint_count": len(sprints),
                "total_skills": data.get("total_skills", 0),
                "total_commits": data.get("total_commits", 0),
                "release_count": data.get("release_count", 0),
                "stories_since_release": data.get("stories_since_release", 0),
                "domain_baselines": data.get("domain_baselines", {}),
                "recent_sprints": sprints[-limit:],
            }
        return {
            "sprint_count": 0,
            "total_skills": 0,
            "total_commits": 0,
            "release_count": 0,
            "stories_since_release": 0,
            "domain_baselines": {},
            "recent_sprints": [],
        }
    finally:
        await r.aclose()
