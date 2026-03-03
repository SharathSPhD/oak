__pattern__ = "Repository"

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ── Enums (matching schema CHECK constraints) ────────────────────────────────

class ProblemStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETE = "complete"
    FAILED = "failed"


class TaskType(str, Enum):
    INGEST = "ingest"
    ANALYSE = "analyse"
    MODEL = "model"
    SYNTHESISE = "synthesise"
    VALIDATE = "validate"


class TaskStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    COMPLETE = "complete"
    FAILED = "failed"


# ── Problems ────────────────────────────────────────────────────────────────

class ProblemCreate(BaseModel):
    title: str
    description: str | None = None
    idempotency_key: str | None = None


class ProblemResponse(BaseModel):
    id: UUID
    title: str
    description: str | None
    status: ProblemStatus
    solution_url: str | None = None
    idempotency_key: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Tasks ────────────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    problem_id: UUID
    title: str
    description: str | None = None
    task_type: TaskType
    assigned_to: str | None = None
    blocked_by: list[UUID] = Field(default_factory=list)


class TaskResponse(BaseModel):
    id: UUID
    problem_id: UUID
    title: str
    description: str | None = None
    task_type: TaskType
    status: TaskStatus
    assigned_to: str | None = None
    blocked_by: list[UUID] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


# ── Agents ───────────────────────────────────────────────────────────────────

class AgentStatusResponse(BaseModel):
    agent_id: str
    role: str
    problem_uuid: str | None = None
    status: str  # idle | running | terminated
    container_id: str | None = None
    last_seen: datetime | None = None


# ── Skills ───────────────────────────────────────────────────────────────────

class SkillResponse(BaseModel):
    id: UUID
    name: str
    category: str
    status: str  # probationary | permanent | deprecated
    use_count: int
    description: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Telemetry ────────────────────────────────────────────────────────────────

class TelemetryEvent(BaseModel):
    agent_id: str
    event_type: str
    problem_uuid: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp_utc: float


# ── Internal Events (hook relay) ────────────────────────────────────────────

class InternalEvent(BaseModel):
    agent_id: str
    event_type: str
    problem_uuid: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp_utc: float = Field(
        default_factory=lambda: __import__("time").time()
    )
