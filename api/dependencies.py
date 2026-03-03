__pattern__ = "Repository"

from functools import lru_cache

from api.config import OAKSettings
from api.events.bus import (
    EpisodicMemorySubscriber,
    EventBus,
    TelemetrySubscriber,
    WebSocketSubscriber,
)


@lru_cache
def get_settings() -> OAKSettings:
    return OAKSettings()


_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        bus = EventBus()
        bus.subscribe(TelemetrySubscriber())
        bus.subscribe(EpisodicMemorySubscriber())
        bus.subscribe(WebSocketSubscriber())
        _event_bus = bus
    return _event_bus
