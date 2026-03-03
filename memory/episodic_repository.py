__pattern__ = "Repository"

from uuid import UUID

import asyncpg

from api.config import settings
from memory.interfaces import Episode, EpisodicMemoryRepository


class PostgreSQLEpisodicRepository(EpisodicMemoryRepository):
    def __init__(self, conn_str: str | None = None) -> None:
        self._conn_str = conn_str or settings.database_url

    async def store(self, episode: Episode) -> UUID:
        conn = await asyncpg.connect(self._conn_str)
        try:
            row = await conn.fetchrow(
                """INSERT INTO episodes (problem_id, agent_id, event_type, content, embedding)
                   VALUES ($1, $2, $3, $4, $5) RETURNING id""",
                episode.problem_id, episode.agent_id, episode.event_type,
                episode.content, episode.embedding
            )
            return row["id"]
        finally:
            await conn.close()

    async def retrieve_similar(self, query_embedding: list[float], top_k: int = 5) -> list[Episode]:
        conn = await asyncpg.connect(self._conn_str)
        try:
            rows = await conn.fetch(
                """SELECT * FROM episodes
                   WHERE embedding IS NOT NULL AND archived_at IS NULL
                   ORDER BY embedding <=> $1::vector
                   LIMIT $2""",
                query_embedding, top_k
            )
            return [_row_to_episode(r) for r in rows]
        finally:
            await conn.close()

    async def mark_retrieved(self, episode_id: UUID) -> None:
        conn = await asyncpg.connect(self._conn_str)
        try:
            await conn.execute(
                """UPDATE episodes SET retrieved_count = retrieved_count + 1,
                   last_retrieved_at = NOW() WHERE id = $1""",
                episode_id
            )
        finally:
            await conn.close()


def _row_to_episode(row: asyncpg.Record) -> Episode:
    return Episode(
        id=row["id"], problem_id=row["problem_id"], agent_id=row["agent_id"],
        event_type=row["event_type"], content=row["content"],
        embedding=list(row["embedding"]) if row["embedding"] else None,
        retrieved_count=row["retrieved_count"], last_retrieved_at=row["last_retrieved_at"],
        archived_at=row["archived_at"], created_at=row["created_at"],
    )
