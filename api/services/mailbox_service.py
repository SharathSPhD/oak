"""Mailbox service — agent-to-agent message passing."""
__pattern__ = "Repository"

import json
import time

try:
    import redis.asyncio as aioredis
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False


class MailboxService:
    """Routes messages between agents via Redis pub/sub + DB persistence."""

    CHANNEL_PREFIX = "oak:mailbox:"

    def __init__(self, redis_url: str) -> None:
        self._redis: aioredis.Redis | None = None
        if _REDIS_AVAILABLE:
            self._redis = aioredis.from_url(redis_url, decode_responses=True)

    async def publish(self, to_agent: str, message_id: str, body: str) -> None:
        """Publish message notification to agent's Redis channel."""
        if self._redis is None:
            return
        try:
            channel = f"{self.CHANNEL_PREFIX}{to_agent}"
            payload = json.dumps({"message_id": message_id, "body": body, "ts": time.time()})
            await self._redis.publish(channel, payload)
        except Exception:
            pass  # Redis down — DB record still persisted

    async def get_unread_count(self, to_agent: str) -> int:
        """Return number of pending notifications in Redis for agent."""
        if self._redis is None:
            return 0
        try:
            key = f"{self.CHANNEL_PREFIX}{to_agent}:count"
            val = await self._redis.get(key)
            return int(val) if val else 0
        except Exception:
            return 0
