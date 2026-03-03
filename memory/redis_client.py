__pattern__ = "Repository"

import redis.asyncio as redis

from memory.interfaces import SessionState, WorkingMemoryRepository


class RedisWorkingMemoryRepository(WorkingMemoryRepository):
    """Production: per-agent key-value store with TTL."""

    def __init__(self, redis_url: str, ttl_hours: int) -> None:
        self._client = redis.from_url(redis_url, decode_responses=True)
        self._ttl = ttl_hours * 3600

    def _key(self, agent_id: str, key: str) -> str:
        return f"oak:session:{agent_id}:{key}"

    async def set(self, agent_id: str, key: str, value: str) -> None:
        await self._client.setex(self._key(agent_id, key), self._ttl, value)

    async def get(self, agent_id: str, key: str) -> str | None:
        return await self._client.get(self._key(agent_id, key))

    async def restore_session(self, agent_id: str) -> SessionState:
        prefix = f"oak:session:{agent_id}:"
        keys = await self._client.keys(f"{prefix}*")
        data: dict[str, str] = {}
        for key in keys:
            val = await self._client.get(key)
            if val is not None:
                category = key[len(prefix):]
                data[category] = val
        return SessionState(agent_id=agent_id, keys=data)
