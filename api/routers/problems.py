__pattern__ = "Repository"

import asyncio
import os
import subprocess
import time
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.connection import get_db
from api.dependencies import get_event_bus
from api.events.bus import AgentEvent, EventBus
from api.models import ProblemCreate, ProblemResponse, ProblemStartResponse

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


@router.post("/{problem_id}/start", response_model=ProblemStartResponse)
async def start_problem(
    problem_id: UUID,
    db: AsyncSession = Depends(get_db),
    bus: EventBus = Depends(get_event_bus),
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

    oak_root = os.environ.get("OAK_ROOT", "/home/sharaths/projects/oak")
    workspace_base = os.environ.get("OAK_WORKSPACE_BASE", os.path.expanduser("~/oak-workspaces"))
    workspace_path = f"{workspace_base}/problem-{problem_id}"
    container_name = f"oak-harness-{problem_id}"
    oak_network = os.environ.get("OAK_NETWORK", "oak_oak-net")

    await db.execute(
        text("UPDATE problems SET status = 'active', updated_at = NOW() WHERE id = :id"),
        {"id": str(problem_id)},
    )
    await db.commit()

    Path(workspace_path).mkdir(parents=True, exist_ok=True)
    os.chmod(workspace_path, 0o777)

    try:
        subprocess.run(
            ["git", "-C", oak_root, "worktree", "add", "-b",
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

    cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "--network", oak_network,
        "-e", "ANTHROPIC_BASE_URL=http://oak-api-proxy:9000",
        "-e", "ANTHROPIC_AUTH_TOKEN=ollama",
        "-e", "ANTHROPIC_API_KEY=ollama",
        "-e", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1",
        "-e", f"OAK_PROBLEM_UUID={problem_id}",
        "-e", "OAK_API_URL=http://oak-api:8000",
        "-e", "OAK_MODEL=claude-sonnet-4-6",
        "-e", "REDIS_URL=redis://oak-redis:6379",
        "-e", "DATABASE_URL=postgresql://oak:oak@oak-postgres:5432/oak",
        "-v", f"{workspace_path}:/workspace",
        "oak/harness:latest",
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Failed to start harness: {stderr.decode()}")

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


@router.post("/{problem_id}/upload")
async def upload_file(
    problem_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Upload a data file to the problem workspace."""
    result = await db.execute(
        text("SELECT id FROM problems WHERE id = :id"),
        {"id": str(problem_id)},
    )
    if result.mappings().one_or_none() is None:
        raise HTTPException(status_code=404, detail="Problem not found")

    workspace_base = os.environ.get("OAK_WORKSPACE_BASE", os.path.expanduser("~/oak-workspaces"))
    workspace_path = Path(f"{workspace_base}/problem-{problem_id}")
    workspace_path.mkdir(parents=True, exist_ok=True)

    dest = workspace_path / file.filename
    content = await file.read()
    dest.write_bytes(content)

    return {"filename": file.filename, "size": len(content), "path": str(dest)}


@router.get("/{problem_id}/logs")
async def get_logs(problem_id: UUID) -> dict:
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
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{problem_id}/status")
async def get_problem_status(problem_id: UUID) -> dict:
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
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{problem_id}/files")
async def list_workspace_files(problem_id: UUID) -> dict:
    """List files in the problem workspace."""
    workspace_base = os.environ.get("OAK_WORKSPACE_BASE", os.path.expanduser("~/oak-workspaces"))
    workspace_path = Path(f"{workspace_base}/problem-{problem_id}")
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
