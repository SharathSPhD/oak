__pattern__ = "Observer"

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class AgentEvent:
    # tool_called | task_claimed | task_complete | judge_verdict | agent_spawned
    event_type: str
    agent_id: str
    problem_uuid: str
    payload: dict[str, Any]
    timestamp_utc: float


class EventSubscriber(ABC):
    @abstractmethod
    async def on_event(self, event: AgentEvent) -> None: ...


class TelemetrySubscriber(EventSubscriber):
    """Writes to agent_telemetry table on tool_called, task_complete, judge_verdict events."""

    async def on_event(self, event: AgentEvent) -> None:
        valid = ("tool_called", "task_complete", "judge_verdict", "agent_spawned")
        if event.event_type not in valid:
            return
        try:
            import json as _json

            import asyncpg

            from api.config import settings as _settings
            conn = await asyncpg.connect(_settings.database_url)
            try:
                problem_id = (
                    event.problem_uuid
                    if event.problem_uuid not in ("", "unknown")
                    else None
                )
                tool_input = event.payload.get("tool_input")
                tool_input_json = (
                    _json.dumps(tool_input) if tool_input else None
                )
                await conn.execute(
                    """INSERT INTO agent_telemetry
                       (problem_id, agent_id, event_type,
                        tool_name, tool_input, duration_ms, escalated)
                       VALUES ($1::uuid, $2, $3, $4,
                               $5::jsonb, $6, $7)""",
                    problem_id,
                    event.agent_id,
                    event.event_type,
                    event.payload.get("tool_name"),
                    tool_input_json,
                    event.payload.get("duration_ms"),
                    bool(event.payload.get("escalated", False)),
                )
            finally:
                await conn.close()
        except Exception:
            pass  # Never block the producer


class WebSocketSubscriber(EventSubscriber):
    """Publishes every event to Redis pub/sub channel oak:stream:{problem_uuid}."""

    async def on_event(self, event: AgentEvent) -> None:
        if event.problem_uuid in ("", "unknown"):
            return
        try:
            import json as _json

            import redis.asyncio as _redis

            from api.config import settings as _settings
            r = _redis.from_url(_settings.redis_url, decode_responses=True)
            try:
                channel = f"oak:stream:{event.problem_uuid}"
                payload = _json.dumps({
                    "event_type": event.event_type,
                    "agent_id": event.agent_id,
                    "timestamp": event.timestamp_utc,
                    "payload": event.payload,
                })
                await r.publish(channel, payload)
            finally:
                await r.aclose()
        except Exception:
            pass


class EpisodicMemorySubscriber(EventSubscriber):
    """Writes task_complete and judge_verdict events to episodes table with embeddings."""

    @staticmethod
    async def _generate_embedding(text: str) -> list[float] | None:
        """Generate embedding via Ollama. Returns None on failure (non-blocking)."""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "http://oak-ollama:11434/api/embeddings",
                    json={"model": "nomic-embed-text", "prompt": text[:8000]},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("embedding")
        except Exception:
            pass
        return None

    async def on_event(self, event: AgentEvent) -> None:
        if event.event_type not in ("task_complete", "judge_verdict"):
            return
        try:
            import json as _json

            import asyncpg

            from api.config import settings as _settings
            content = _json.dumps(event.payload)
            embedding = await self._generate_embedding(content)
            conn = await asyncpg.connect(_settings.database_url)
            try:
                problem_id = (
                    event.problem_uuid
                    if event.problem_uuid not in ("", "unknown")
                    else None
                )
                await conn.execute(
                    """INSERT INTO episodes
                       (problem_id, agent_id, event_type, content, embedding)
                       VALUES ($1::uuid, $2, $3, $4, $5::vector)""",
                    problem_id,
                    event.agent_id,
                    event.event_type,
                    content,
                    embedding if embedding else None,
                )
            finally:
                await conn.close()
        except Exception:
            pass


class SessionStateSubscriber(EventSubscriber):
    """Updates oak:session:{agent_id} keys in Redis after tool calls."""

    async def on_event(self, event: AgentEvent) -> None:
        try:
            from api.config import OAKSettings
            from api.services.agent_registry import AgentRegistry
            registry = AgentRegistry(str(OAKSettings().redis_url))
            if event.event_type == "agent_spawned":
                role = event.payload.get("role", "")
                await registry.register(
                    event.agent_id, role, event.problem_uuid,
                )
            elif event.event_type == "agent_terminated":
                await registry.update_status(event.agent_id, "terminated")
            elif event.event_type == "tool_called":
                await registry.touch(event.agent_id)
        except Exception:
            pass


class EventBus:
    """Synchronous publish; async subscribers fire concurrently via asyncio.gather."""

    def __init__(self) -> None:
        self._subscribers: list[EventSubscriber] = []

    def subscribe(self, subscriber: EventSubscriber) -> None:
        self._subscribers.append(subscriber)

    async def publish(self, event: AgentEvent) -> None:
        await asyncio.gather(*[s.on_event(event) for s in self._subscribers],
                             return_exceptions=True)  # Never block the producer
