__pattern__ = "Repository"

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# ── Enums (matching schema CHECK constraints) ────────────────────────────────

class ProblemStatus(StrEnum):
    PENDING = "pending"
    ASSEMBLING = "assembling"
    ACTIVE = "active"
    COMPLETE = "complete"
    FAILED = "failed"


class TaskType(StrEnum):
    INGEST = "ingest"
    ANALYSE = "analyse"
    MODEL = "model"
    SYNTHESISE = "synthesise"
    VALIDATE = "validate"


class TaskStatus(StrEnum):
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


class ProblemStartResponse(BaseModel):
    id: UUID
    status: str
    container_name: str
    workspace_path: str
    message: str


class ProblemStatusUpdate(BaseModel):
    status: ProblemStatus


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


class TelemetryEventCreate(BaseModel):
    """Record a single agent telemetry event."""
    problem_id: UUID | None = None
    agent_id: str
    event_type: str  # e.g. "tool_called", "agent_spawned", "agent_terminated", "escalation"
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_response: dict[str, Any] | None = None
    duration_ms: int | None = None
    escalated: bool = False


class TelemetryResponse(BaseModel):
    """Aggregated telemetry metrics for the /health + dashboard."""
    total_events: int
    total_escalations: int
    escalation_rate_pct: float  # escalations / total_events * 100
    events_by_type: dict[str, int]
    active_problems: int
    recent_events: list[dict[str, Any]]  # last 20 events (id, agent_id, event_type, created_at)


# ── Internal Events (hook relay) ────────────────────────────────────────────

class InternalEvent(BaseModel):
    agent_id: str
    event_type: str
    problem_uuid: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp_utc: float = Field(
        default_factory=lambda: __import__("time").time()
    )


# ── Mailbox ──────────────────────────────────────────────────────────────────

class MailboxMessageCreate(BaseModel):
    problem_id: UUID
    from_agent: str
    to_agent: str
    subject: str | None = None
    body: str


class MailboxMessageResponse(BaseModel):
    id: UUID
    problem_id: UUID
    from_agent: str
    to_agent: str
    subject: str | None
    body: str
    read_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Judge ────────────────────────────────────────────────────────────────────

class JudgeVerdictCreate(BaseModel):
    task_id: UUID
    verdict: str  # "pass" | "fail"
    checks: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class JudgeVerdictResponse(BaseModel):
    id: UUID
    task_id: UUID
    verdict: str
    checks: dict[str, Any]
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
