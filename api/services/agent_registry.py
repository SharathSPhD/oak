"""Redis-backed agent session registry."""
__pattern__ = "Repository"

import json
import time

from api.models import AgentStatusResponse

try:
    import redis.asyncio as aioredis
    _REDIS_AVAILABLE = True
except ImportError:
    aioredis = None  # type: ignore[assignment]
    _REDIS_AVAILABLE = False


class AgentRegistry:
    """Tracks active agent sessions in Redis. Pattern: Repository."""

    KEY_PREFIX = "oak:agent:"
    TTL = 300

    def __init__(self, redis_url: str) -> None:
        self._redis: aioredis.Redis | None = None
        if _REDIS_AVAILABLE and aioredis:
            self._redis = aioredis.from_url(redis_url, decode_responses=True)

    async def register(
        self, agent_id: str, role: str, problem_uuid: str = "", container_id: str = ""
    ) -> None:
        if self._redis is None:
            return
        key = f"{self.KEY_PREFIX}{agent_id}"
        data = {"agent_id": agent_id, "role": role, "problem_uuid": problem_uuid,
                "status": "running", "container_id": container_id, "last_seen": time.time()}
        await self._redis.set(key, json.dumps(data), ex=self.TTL)

    async def update_status(self, agent_id: str, status: str) -> None:
        if self._redis is None:
            return
        key = f"{self.KEY_PREFIX}{agent_id}"
        raw = await self._redis.get(key)
        if raw:
            data = json.loads(raw)
            data["status"] = status
            data["last_seen"] = time.time()
            await self._redis.set(key, json.dumps(data), ex=self.TTL)

    async def touch(self, agent_id: str) -> None:
        if self._redis is None:
            return
        key = f"{self.KEY_PREFIX}{agent_id}"
        raw = await self._redis.get(key)
        if raw:
            data = json.loads(raw)
            data["last_seen"] = time.time()
            await self._redis.set(key, json.dumps(data), keepttl=True)

    async def get_all(self) -> list[AgentStatusResponse]:
        if self._redis is None:
            return []
        try:
            keys = await self._redis.keys(f"{self.KEY_PREFIX}*")
            result = []
            for key in keys:
                raw = await self._redis.get(key)
                if raw:
                    d = json.loads(raw)
                    result.append(AgentStatusResponse(
                        agent_id=d["agent_id"], role=d["role"],
                        problem_uuid=d.get("problem_uuid"),
                        status=d["status"], container_id=d.get("container_id"),
                        last_seen=None,
                    ))
            return result
        except Exception:
            return []
