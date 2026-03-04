__pattern__ = "Decorator"

import time
from collections import OrderedDict
from uuid import UUID

from memory.interfaces import Skill, SkillRepository


class CachedSkillRepository(SkillRepository):
    """
    Decorator: wraps any SkillRepository with LRU in-memory caching.

    Caches find_by_keywords() results to avoid repeated DB round-trips
    for identical queries within a single agent session (5-minute TTL).
    """

    def __init__(
        self,
        wrapped: SkillRepository,
        max_size: int = 128,
        ttl_seconds: float = 300.0,
    ) -> None:
        self._wrapped = wrapped
        self._max_size = max_size
        self._ttl = ttl_seconds
        # OrderedDict as LRU: key → (timestamp, results)
        self._cache: OrderedDict[tuple[str, str | None, int], tuple[float, list[Skill]]] = (
            OrderedDict()
        )

    async def find_by_keywords(
        self, query: str, category: str | None = None, top_k: int = 5
    ) -> list[Skill]:
        cache_key = (query, category, top_k)
        now = time.monotonic()

        if cache_key in self._cache:
            ts, results = self._cache[cache_key]
            if now - ts < self._ttl:
                self._cache.move_to_end(cache_key)  # LRU refresh
                return results
            del self._cache[cache_key]

        results = await self._wrapped.find_by_keywords(query, category, top_k)

        if len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)  # evict oldest
        self._cache[cache_key] = (now, results)
        return results

    async def promote(self, skill_id: UUID) -> None:
        await self._wrapped.promote(skill_id)

    async def deprecate(self, skill_id: UUID, reason: str) -> None:
        await self._wrapped.deprecate(skill_id, reason)
