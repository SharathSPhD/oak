__pattern__ = "Repository"

from uuid import UUID

import asyncpg

from api.config import settings
from memory.interfaces import PromotionThresholdNotMet, Skill, SkillRepository


class PostgreSQLSkillRepository(SkillRepository):
    """PostgreSQL-backed SkillRepository with pgvector similarity search."""

    def __init__(self, conn_str: str | None = None) -> None:
        self._conn_str = conn_str or settings.database_url

    async def find_by_keywords(
        self, query: str, category: str | None = None, top_k: int = 5
    ) -> list[Skill]:
        conn = await asyncpg.connect(self._conn_str)
        try:
            if category:
                rows = await conn.fetch(
                    """SELECT * FROM skills
                       WHERE status != 'deprecated'
                         AND category = $1
                         AND ($2 = ANY(trigger_keywords) OR name ILIKE $3)
                       LIMIT $4""",
                    category, query, f"%{query}%", top_k
                )
            else:
                rows = await conn.fetch(
                    """SELECT * FROM skills
                       WHERE status != 'deprecated'
                         AND ($1 = ANY(trigger_keywords) OR name ILIKE $2)
                       LIMIT $3""",
                    query, f"%{query}%", top_k
                )
            return [_row_to_skill(r) for r in rows]
        finally:
            await conn.close()

    async def promote(self, skill_id: UUID) -> None:
        conn = await asyncpg.connect(self._conn_str)
        try:
            row = await conn.fetchrow(
                "SELECT verified_on_problems FROM skills WHERE id = $1", skill_id
            )
            if row is None:
                raise ValueError(f"Skill {skill_id} not found")
            threshold = settings.oak_skill_promo_threshold
            verified = row["verified_on_problems"] or []
            if len(verified) < threshold:
                raise PromotionThresholdNotMet(
                    f"Need {threshold} verified problems, have {len(verified)}"
                )
            await conn.execute(
                "UPDATE skills SET status='permanent', updated_at=NOW() WHERE id=$1", skill_id
            )
        finally:
            await conn.close()

    async def deprecate(self, skill_id: UUID, reason: str) -> None:
        conn = await asyncpg.connect(self._conn_str)
        try:
            await conn.execute(
                """UPDATE skills SET status='deprecated', deprecated_reason=$1,
                   updated_at=NOW() WHERE id=$2""",
                reason, skill_id
            )
        finally:
            await conn.close()


def _row_to_skill(row: asyncpg.Record) -> Skill:
    from uuid import UUID as _UUID
    return Skill(
        id=row["id"],
        name=row["name"],
        category=row["category"],
        description=row["description"],
        trigger_keywords=list(row["trigger_keywords"] or []),
        embedding=list(row["embedding"]) if row["embedding"] else None,
        status=row["status"],
        use_count=row["use_count"],
        verified_on_problems=[_UUID(str(u)) for u in (row["verified_on_problems"] or [])],
        filesystem_path=row["filesystem_path"],
        deprecated_reason=row["deprecated_reason"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
