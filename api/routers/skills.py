__pattern__ = "Repository"

from uuid import UUID

import asyncpg
from fastapi import APIRouter, HTTPException, Query

from api.config import settings
from memory.interfaces import PromotionThresholdNotMet
from memory.skill_repository import PostgreSQLSkillRepository, _row_to_skill

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("")
async def list_skills(
    query: str | None = Query(default=None),
    category: str | None = Query(default=None),
    status: str = Query(default="permanent"),
    top_k: int = Query(default=10, ge=1, le=50),
) -> list[dict]:  # noqa: ANN202
    repo = PostgreSQLSkillRepository()
    try:
        if query:
            skills = await repo.find_by_keywords(query, category=category, top_k=top_k)
        else:
            conn = await asyncpg.connect(settings.database_url)
            try:
                params: list = [status]
                q = "SELECT * FROM skills WHERE status = $1"
                if category:
                    params.append(category)
                    q += f" AND category = ${len(params)}"
                q += " ORDER BY use_count DESC LIMIT 50"
                rows = await conn.fetch(q, *params)
                skills = [_row_to_skill(r) for r in rows]
            finally:
                await conn.close()
        return [
            {
                "id": str(s.id), "name": s.name, "category": s.category,
                "description": s.description, "trigger_keywords": s.trigger_keywords,
                "status": s.status, "use_count": s.use_count,
                "verified_on_problems": [str(p) for p in s.verified_on_problems],
                "filesystem_path": s.filesystem_path,
            }
            for s in skills
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{skill_id}/promote")
async def promote_skill(skill_id: UUID) -> dict:  # noqa: ANN202
    repo = PostgreSQLSkillRepository()
    try:
        await repo.promote(skill_id)
        return {"status": "promoted", "skill_id": str(skill_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PromotionThresholdNotMet as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
