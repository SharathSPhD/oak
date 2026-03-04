__pattern__ = "Repository"

from uuid import UUID

from memory.episodic_repository import PostgreSQLEpisodicRepository
from memory.interfaces import Episode, EpisodicMemoryRepository


class PostgresEpisodicMemoryRepository(EpisodicMemoryRepository):
    """Production: delegates to PostgreSQLEpisodicRepository (asyncpg + pgvector)."""

    def __init__(self, db_url: str) -> None:
        self._db_url = db_url
        self._delegate = PostgreSQLEpisodicRepository(conn_str=db_url)

    async def store(self, episode: Episode) -> UUID:
        return await self._delegate.store(episode)

    async def retrieve_similar(self, query_embedding: list[float], top_k: int = 5) -> list[Episode]:
        return await self._delegate.retrieve_similar(query_embedding, top_k)

    async def retrieve_global(
        self, embedding: list[float], limit: int = 10
    ) -> list[dict[str, object]]:
        return await self._delegate.retrieve_global(embedding, limit)

    async def mark_retrieved(self, episode_id: UUID) -> None:
        await self._delegate.mark_retrieved(episode_id)
