"""Unit tests for judge verdict models."""
import pytest
from uuid import uuid4
from api.models import JudgeVerdictCreate, JudgeVerdictResponse


def test_judge__verdict_create__accepts_pass():
    v = JudgeVerdictCreate(task_id=uuid4(), verdict="pass")
    assert v.verdict == "pass"
    assert v.checks == {}


def test_judge__verdict_create__accepts_fail_with_checks():
    v = JudgeVerdictCreate(
        task_id=uuid4(), verdict="fail",
        checks={"linting": False, "tests": True},
        notes="Linting failed",
    )
    assert v.verdict == "fail"
    assert v.checks["linting"] is False


def test_judge__verdict_create__requires_task_id():
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        JudgeVerdictCreate(verdict="pass")  # type: ignore[call-arg]


def test_judge__verdict_response__from_dict():
    from datetime import datetime, timezone
    r = JudgeVerdictResponse(
        id=uuid4(), task_id=uuid4(), verdict="pass",
        checks={}, notes=None, created_at=datetime.now(timezone.utc),
    )
    assert r.verdict == "pass"
