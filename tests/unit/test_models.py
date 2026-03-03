"""Unit tests for Pydantic model validation."""
import pytest
from datetime import datetime
from uuid import uuid4

from api.models import (
    ProblemCreate,
    ProblemResponse,
    TaskCreate,
    TaskStatusUpdate,
    TelemetryEvent,
    InternalEvent,
    TaskType,
    TaskStatus,
)


def test_models__problem_create__rejects_missing_title():
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        ProblemCreate(description="no title")


def test_models__problem_create__accepts_optional_fields():
    p = ProblemCreate(title="Test")
    assert p.description is None
    assert p.idempotency_key is None


def test_models__problem_response__from_attributes():
    p = ProblemResponse(
        id=uuid4(),
        title="T",
        description="D",
        status="pending",
        created_at=datetime.utcnow(),
    )
    assert p.status == "pending"
    assert p.solution_url is None


def test_models__task_create__requires_task_type():
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        TaskCreate(problem_id=uuid4(), title="T")


def test_models__task_status_update__accepts_valid_status():
    t = TaskStatusUpdate(status="claimed")
    assert t.status == TaskStatus.CLAIMED


def test_models__task_status_update__rejects_invalid_status():
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        TaskStatusUpdate(status="invalid_status")


def test_models__telemetry_event__requires_timestamp():
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        TelemetryEvent(agent_id="a", event_type="tool_called", problem_uuid="p-1")


def test_models__internal_event__timestamp_defaults():
    e = InternalEvent(agent_id="a", event_type="tool_called")
    assert e.timestamp_utc > 0
    assert e.problem_uuid == ""
