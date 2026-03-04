__pattern__ = "StateMachine"

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.connection import get_db
from api.models import TaskCreate, TaskResponse, TaskStatusUpdate
from api.state_machines.task import IllegalTransitionError, TaskStateMachine, TaskStatus

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreate,
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    task_id = uuid4()
    blocked_by_strs = [str(uid) for uid in body.blocked_by]
    result = await db.execute(
        text("""
            INSERT INTO tasks
            (id, problem_id, title, description, task_type, status, assigned_to,
            blocked_by)
            VALUES
            (:id, :problem_id, :title, :description, :task_type, 'pending',
            :assigned_to, :blocked_by)
            RETURNING id, problem_id, title, description, task_type, status, assigned_to,
            blocked_by, created_at, updated_at
        """),
        {
            "id": str(task_id),
            "problem_id": str(body.problem_id),
            "title": body.title,
            "description": body.description,
            "task_type": body.task_type.value,
            "assigned_to": body.assigned_to,
            "blocked_by": blocked_by_strs,
        },
    )
    await db.commit()
    row = dict(result.mappings().one())
    if row.get("blocked_by") and isinstance(row["blocked_by"], list):
        row["blocked_by"] = [UUID(s) if isinstance(s, str) else s for s in row["blocked_by"]]
    return TaskResponse(**row)


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    problem_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
) -> list[TaskResponse]:
    result = await db.execute(
        text("""
            SELECT id, problem_id, title, description, task_type, status, assigned_to,
            blocked_by, created_at, updated_at
            FROM tasks WHERE problem_id = :problem_id ORDER BY created_at
        """),
        {"problem_id": str(problem_id)},
    )
    rows = []
    for row in result.mappings():
        d = dict(row)
        if d.get("blocked_by") and isinstance(d["blocked_by"], list):
            d["blocked_by"] = [UUID(s) if isinstance(s, str) else s for s in d["blocked_by"]]
        rows.append(TaskResponse(**d))
    return rows


@router.patch("/{task_id}/status", response_model=TaskResponse)
async def update_task_status(
    task_id: UUID,
    body: TaskStatusUpdate,
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    result = await db.execute(
        text("SELECT status FROM tasks WHERE id = :id"),
        {"id": str(task_id)},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")

    sm = TaskStateMachine(TaskStatus(row["status"]))
    try:
        sm.transition(TaskStatus(body.status.value))
    except IllegalTransitionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    updated = await db.execute(
        text("""
            UPDATE tasks SET status = :status, updated_at = NOW() WHERE id = :id
            RETURNING id, problem_id, title, description, task_type, status, assigned_to,
            blocked_by, created_at, updated_at
        """),
        {"status": sm.state.value, "id": str(task_id)},
    )
    await db.commit()
    d = dict(updated.mappings().one())
    if d.get("blocked_by") and isinstance(d["blocked_by"], list):
        d["blocked_by"] = [UUID(s) if isinstance(s, str) else s for s in d["blocked_by"]]
    return TaskResponse(**d)
