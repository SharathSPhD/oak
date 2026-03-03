__pattern__ = "Observer"

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class AgentEvent:
    event_type: str          # tool_called | task_claimed | task_complete | judge_verdict | agent_spawned
    agent_id: str
    problem_uuid: str
    payload: dict[str, Any]
    timestamp_utc: float


class EventSubscriber(ABC):
    @abstractmethod
    async def on_event(self, event: AgentEvent) -> None: ...


class TelemetrySubscriber(EventSubscriber):
    """Writes to agent_telemetry table on every tool_called event."""

    async def on_event(self, event: AgentEvent) -> None:
        # TODO Phase 2: INSERT into agent_telemetry
        pass


class WebSocketSubscriber(EventSubscriber):
    """Publishes to Redis pub/sub channel oak:stream:{problem_uuid}."""

    async def on_event(self, event: AgentEvent) -> None:
        # TODO Phase 3: PUBLISH to Redis channel
        pass


class EpisodicMemorySubscriber(EventSubscriber):
    """Writes significant events to episodes table with embedding."""

    async def on_event(self, event: AgentEvent) -> None:
        # TODO Phase 3: INSERT into episodes with embedding
        pass


class SessionStateSubscriber(EventSubscriber):
    """Updates oak:session:{agent_id} keys in Redis after tool calls."""

    async def on_event(self, event: AgentEvent) -> None:
        try:
            from api.services.agent_registry import AgentRegistry
            from api.config import OAKSettings
            registry = AgentRegistry(str(OAKSettings().redis_url))
            if event.event_type == "agent_spawned":
                await registry.register(event.agent_id, event.payload.get("role", ""), event.problem_uuid)
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
