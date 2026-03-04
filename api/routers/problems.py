__pattern__ = "Repository"

import asyncio
import os
import subprocess
import time
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import OAKSettings
from api.db.connection import get_db
from api.dependencies import get_event_bus, get_settings
from api.events.bus import AgentEvent, EventBus
from api.factories.agent_factory import ResourceCapExceededError, get_agent_factory
from api.models import (
    ProblemCreate,
    ProblemResponse,
    ProblemStartResponse,
    ProblemStatusUpdate,
    SpawnAgentRequest,
)

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


@router.post("/cleanup")
async def cleanup_stale_problems(
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Find active/assembling problems whose harness containers have exited and mark as failed."""
    result = await db.execute(
        text("SELECT id, status FROM problems WHERE status IN ('active', 'assembling')"),
    )
    rows = result.mappings().all()
    cleaned = 0

    for row in rows:
        container_name = f"oak-harness-{row['id']}"
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "inspect", "--format", "{{.State.Running}}", container_name,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            running = stdout.decode().strip().lower()
            if running != "true":
                await db.execute(
                    text(
                        "UPDATE problems SET status = 'failed',"
                        " updated_at = NOW() WHERE id = :id"
                    ),
                    {"id": str(row["id"])},
                )
                cleaned += 1
        except Exception:
            await db.execute(
                text(
                    "UPDATE problems SET status = 'failed',"
                    " updated_at = NOW() WHERE id = :id"
                ),
                {"id": str(row["id"])},
            )
            cleaned += 1

    await db.commit()
    return {"cleaned": cleaned, "total_checked": len(rows)}


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


@router.post("/{problem_id}/start", response_model=ProblemStartResponse)
async def start_problem(
    problem_id: UUID,
    db: AsyncSession = Depends(get_db),
    bus: EventBus = Depends(get_event_bus),
    settings: OAKSettings = Depends(get_settings),
) -> ProblemStartResponse:
    """Start the agent pipeline for a problem. Creates worktree + launches harness."""
    result = await db.execute(
        text("SELECT id, status FROM problems WHERE id = :id"),
        {"id": str(problem_id)},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    if row["status"] not in ("pending", "failed"):
        raise HTTPException(status_code=409, detail=f"Problem is already {row['status']}")

    workspace_path = f"{settings.oak_workspace_base}/problem-{problem_id}"
    container_name = f"oak-harness-{problem_id}"

    await db.execute(
        text("UPDATE problems SET status = 'active', updated_at = NOW() WHERE id = :id"),
        {"id": str(problem_id)},
    )
    await db.commit()

    Path(workspace_path).mkdir(parents=True, exist_ok=True)
    os.chmod(workspace_path, 0o777)

    try:
        subprocess.run(
            ["git", "-C", settings.oak_root, "worktree", "add", "-b",
             f"oak/problem-{problem_id}", workspace_path, "main"],
            capture_output=True, timeout=30,
        )
    except Exception:
        pass

    try:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass

    factory = get_agent_factory()
    spec = factory.create(
        role="orchestrator",
        problem_uuid=str(problem_id),
        container_name=container_name,
    )
    spec.network = settings.oak_network
    spec.workspace_path = workspace_path

    try:
        await factory.launch(spec)
    except ResourceCapExceededError as e:
        raise HTTPException(status_code=500, detail=f"Failed to start harness: {e}") from e

    await bus.publish(AgentEvent(
        event_type="problem_started",
        agent_id="system",
        problem_uuid=str(problem_id),
        timestamp_utc=time.time(),
        payload={"container": container_name},
    ))

    return ProblemStartResponse(
        id=problem_id,
        status="active",
        container_name=container_name,
        workspace_path=workspace_path,
        message=f"Pipeline started in container {container_name}",
    )


@router.post("/{problem_id}/spawn-agent")
async def spawn_agent(
    problem_id: UUID,
    body: SpawnAgentRequest,
    settings: OAKSettings = Depends(get_settings),
) -> dict[str, str]:
    """Spawn a specialist agent container for a specific role."""
    workspace_path = f"{settings.oak_workspace_base}/problem-{problem_id}"
    suffix = str(body.task_id)[:8] if body.task_id else str(uuid4())[:8]
    container_name = f"oak-{body.role}-{suffix}"

    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "rm", "-f", container_name,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
    except Exception:
        pass

    factory = get_agent_factory()
    kwargs: dict[str, str] = {"container_name": container_name}
    if body.task_id:
        kwargs["task_id"] = body.task_id
    spec = factory.create(role=body.role, problem_uuid=str(problem_id), **kwargs)
    spec.network = settings.oak_network
    spec.workspace_path = workspace_path

    try:
        container_id = await factory.launch(spec)
    except ResourceCapExceededError as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to spawn {body.role}: {e}"
        ) from e

    return {
        "container_name": container_name,
        "container_id": container_id,
        "role": body.role,
        "model": spec.model,
    }


@router.post("/{problem_id}/upload")
async def upload_file(
    problem_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    settings: OAKSettings = Depends(get_settings),
) -> dict[str, object]:
    """Upload a data file to the problem workspace."""
    result = await db.execute(
        text("SELECT id FROM problems WHERE id = :id"),
        {"id": str(problem_id)},
    )
    if result.mappings().one_or_none() is None:
        raise HTTPException(status_code=404, detail="Problem not found")

    workspace_path = Path(f"{settings.oak_workspace_base}/problem-{problem_id}")
    workspace_path.mkdir(parents=True, exist_ok=True)

    fname = file.filename or "uploaded_file"
    dest = workspace_path / fname
    content = await file.read()
    dest.write_bytes(content)

    return {"filename": fname, "size": len(content), "path": str(dest)}


@router.get("/{problem_id}/logs")
async def get_logs(problem_id: UUID) -> dict[str, str]:
    """Get harness container logs for a problem."""
    container_name = f"oak-harness-{problem_id}"
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "logs", "--tail", "100", container_name,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        return {"container": container_name, "logs": stdout.decode(errors="replace")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{problem_id}/status")
async def get_problem_status(problem_id: UUID) -> dict[str, str]:
    """Get harness container status for a problem."""
    container_name = f"oak-harness-{problem_id}"
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "ps", "-a", "--filter", f"name={container_name}",
            "--format", "{{.Status}}",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        container_status = stdout.decode().strip() or "not found"
        return {"container": container_name, "container_status": container_status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{problem_id}/files")
async def list_workspace_files(
    problem_id: UUID,
    settings: OAKSettings = Depends(get_settings),
) -> dict[str, object]:
    """List files in the problem workspace."""
    workspace_path = Path(f"{settings.oak_workspace_base}/problem-{problem_id}")
    if not workspace_path.exists():
        return {"files": [], "workspace": str(workspace_path)}
    files = []
    for f in sorted(workspace_path.rglob("*")):
        if f.is_file() and ".git" not in f.parts:
            files.append({
                "name": str(f.relative_to(workspace_path)),
                "size": f.stat().st_size,
            })
    return {"files": files, "workspace": str(workspace_path)}


@router.get("/{problem_id}/files/{filename:path}")
async def get_file_content(
    problem_id: UUID,
    filename: str,
    settings: OAKSettings = Depends(get_settings),
) -> FileResponse:
    """Serve a file from the problem workspace (markdown, images, code, etc)."""
    workspace = Path(f"{settings.oak_workspace_base}/problem-{problem_id}")
    filepath = (workspace / filename).resolve()
    if not str(filepath).startswith(str(workspace.resolve())):
        raise HTTPException(status_code=403, detail="Path traversal not allowed")
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(filepath)


@router.patch("/{problem_id}", response_model=ProblemResponse)
async def update_problem_status(
    problem_id: UUID,
    body: ProblemStatusUpdate,
    db: AsyncSession = Depends(get_db),
) -> ProblemResponse:
    """Update problem status (e.g. mark as failed, complete, archived)."""
    result = await db.execute(
        text("""
            UPDATE problems SET status = :status, updated_at = NOW()
            WHERE id = :id
            RETURNING id, title, description, status, solution_url,
            idempotency_key, created_at, updated_at
        """),
        {"id": str(problem_id), "status": body.status.value},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    await db.commit()
    return ProblemResponse(**dict(row))


@router.delete("/{problem_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_problem(
    problem_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Hard-delete a problem and stop its harness container if running."""
    result = await db.execute(
        text("SELECT id FROM problems WHERE id = :id"),
        {"id": str(problem_id)},
    )
    if result.mappings().one_or_none() is None:
        raise HTTPException(status_code=404, detail="Problem not found")

    container_name = f"oak-harness-{problem_id}"
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "rm", "-f", container_name,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
    except Exception:
        pass

    await db.execute(text("DELETE FROM tasks WHERE problem_id = :id"), {"id": str(problem_id)})
    await db.execute(text("DELETE FROM mailbox WHERE problem_id = :id"), {"id": str(problem_id)})
    await db.execute(
        text("DELETE FROM agent_telemetry WHERE problem_id = :id"), {"id": str(problem_id)},
    )
    await db.execute(text("DELETE FROM problems WHERE id = :id"), {"id": str(problem_id)})
    await db.commit()
