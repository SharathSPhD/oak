"""Judge verdict router — Phase 2 gate."""
__pattern__ = "Observer"

import time
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.connection import get_db
from api.dependencies import get_event_bus
from api.events.bus import AgentEvent, EventBus
from api.models import JudgeVerdictCreate, JudgeVerdictResponse

router = APIRouter(prefix="/api/judge_verdicts", tags=["judge"])


@router.post("", response_model=JudgeVerdictResponse, status_code=status.HTTP_201_CREATED)
async def submit_verdict(
    body: JudgeVerdictCreate,
    db: AsyncSession = Depends(get_db),
    bus: EventBus = Depends(get_event_bus),
) -> JudgeVerdictResponse:
    """Submit a judge verdict for a task. Publishes judge_verdict event."""
    verdict_id = uuid4()
    result = await db.execute(
        text("""
            INSERT INTO judge_verdicts (id, task_id, verdict, checks, notes)
            VALUES (:id, :task_id, :verdict, CAST(:checks AS jsonb), :notes)
            RETURNING id, task_id, verdict, checks, notes, created_at
        """),
        {
            "id": str(verdict_id),
            "task_id": str(body.task_id),
            "verdict": body.verdict,
            "checks": __import__("json").dumps(body.checks),
            "notes": body.notes,
        },
    )
    await db.commit()
    row = result.mappings().one()
    await bus.publish(AgentEvent(
        event_type="judge_verdict",
        agent_id="judge",
        problem_uuid="",
        payload={"task_id": str(body.task_id), "verdict": body.verdict},
        timestamp_utc=time.time(),
    ))
    return JudgeVerdictResponse(**dict(row))


@router.get("/{problem_uuid}", response_model=list[JudgeVerdictResponse])
async def get_verdicts(
    problem_uuid: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[JudgeVerdictResponse]:
    """Return all judge verdicts for tasks belonging to a problem."""
    result = await db.execute(
        text("""
            SELECT jv.id, jv.task_id, jv.verdict, jv.checks, jv.notes, jv.created_at
            FROM judge_verdicts jv
            JOIN tasks t ON t.id = jv.task_id
            WHERE t.problem_id = :problem_uuid
            ORDER BY jv.created_at DESC
        """),
        {"problem_uuid": str(problem_uuid)},
    )
    return [JudgeVerdictResponse(**dict(row)) for row in result.mappings()]
