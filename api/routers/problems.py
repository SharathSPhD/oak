__pattern__ = "Repository"

import time
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.connection import get_db
from api.dependencies import get_event_bus
from api.events.bus import AgentEvent, EventBus
from api.models import ProblemCreate, ProblemResponse

router = APIRouter(prefix="/api/problems", tags=["problems"])


@router.post("", response_model=ProblemResponse, status_code=status.HTTP_201_CREATED)
async def create_problem(
    body: ProblemCreate,
    db: AsyncSession = Depends(get_db),
    bus: EventBus = Depends(get_event_bus),
) -> ProblemResponse:
    """Create a new problem. Returns 429 if MAX_CONCURRENT_PROBLEMS exceeded."""
    problem_id = uuid4()
    result = await db.execute(
        text("""
            INSERT INTO problems
            (id, title, description, status, idempotency_key)
            VALUES (:id, :title, :description, 'pending', :idempotency_key)
            RETURNING id, title, description, status, solution_url,
            idempotency_key, created_at, updated_at
        """),
        {
            "id": str(problem_id),
            "title": body.title,
            "description": body.description,
            "idempotency_key": body.idempotency_key,
        },
    )
    await db.commit()
    row = result.mappings().one()
    await bus.publish(AgentEvent(
        event_type="problem_created",
        agent_id="system",
        problem_uuid=str(problem_id),
        timestamp_utc=time.time(),
        payload={"title": body.title},
    ))
    return ProblemResponse(**dict(row))


@router.get("", response_model=list[ProblemResponse])
async def list_problems(
    db: AsyncSession = Depends(get_db),
) -> list[ProblemResponse]:
    """List all problems, newest first."""
    result = await db.execute(
        text("""
            SELECT id, title, description, status, solution_url,
            idempotency_key, created_at, updated_at
            FROM problems ORDER BY created_at DESC LIMIT 100
        """),
    )
    rows = result.mappings().all()
    return [ProblemResponse(**dict(r)) for r in rows]


@router.get("/{problem_id}", response_model=ProblemResponse)
async def get_problem(
    problem_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ProblemResponse:
    """Get problem by ID."""
    result = await db.execute(
        text("""
            SELECT id, title, description, status, solution_url,
            idempotency_key, created_at, updated_at
            FROM problems WHERE id = :id
        """),
        {"id": str(problem_id)},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    return ProblemResponse(**dict(row))
