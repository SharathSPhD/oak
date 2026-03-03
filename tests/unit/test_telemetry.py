"""Unit tests for /api/telemetry router."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from api.routers.telemetry import router


@pytest.fixture()
def client():
    """FastAPI TestClient for telemetry router."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _mock_conn(total=10, escalations=2, type_rows=None, active=1, recent=None):
    """Build a mock asyncpg connection with proper async support."""
    mock_conn = AsyncMock()

    # Setup context manager methods
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)

    # Create mock row objects for fetchrow calls
    total_row = MagicMock()
    total_row.__getitem__ = lambda s, k: total if k == "cnt" else None

    esc_row = MagicMock()
    esc_row.__getitem__ = lambda s, k: escalations if k == "cnt" else None

    active_row = MagicMock()
    active_row.__getitem__ = lambda s, k: active if k == "cnt" else None

    # Setup type_rows if not provided
    if type_rows is None:
        type_rows = []
        r = MagicMock()
        r.__getitem__ = lambda s, k, event_type="tool_called", cnt=total: {
            "event_type": event_type, "cnt": cnt
        }[k]
        type_rows = [r]

    # Setup fetch for recent_rows
    if recent is None:
        recent = []

    # Set side effects for fetchrow (called in order: total, escalations, active)
    mock_conn.fetchrow.side_effect = [total_row, esc_row, active_row]
    # Set side effects for fetch (called in order: type_rows, recent_rows)
    mock_conn.fetch.side_effect = [type_rows, recent]
    mock_conn.close = AsyncMock()

    return mock_conn


def test_telemetry__get__returns_200_with_aggregated_metrics(client):
    """Test GET /api/telemetry returns 200 with aggregated metrics."""
    mock_conn = _mock_conn()
    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        resp = client.get("/api/telemetry")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_events" in data
    assert "total_escalations" in data
    assert "escalation_rate_pct" in data
    assert "events_by_type" in data
    assert "active_problems" in data
    assert "recent_events" in data


def test_telemetry__get__zero_events__returns_zero_rate(client):
    """Test GET /api/telemetry with zero events returns 0.0 escalation rate."""
    mock_conn = _mock_conn(total=0, escalations=0)
    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        resp = client.get("/api/telemetry")
    assert resp.status_code == 200
    assert resp.json()["escalation_rate_pct"] == 0.0


def test_telemetry__get__calculates_escalation_rate(client):
    """Test GET /api/telemetry calculates escalation rate correctly."""
    mock_conn = _mock_conn(total=10, escalations=3)
    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        resp = client.get("/api/telemetry")
    assert resp.status_code == 200
    assert resp.json()["escalation_rate_pct"] == 30.0


def test_telemetry__post__records_event(client):
    """Test POST /api/telemetry records a telemetry event."""
    mock_conn = AsyncMock()
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda s, k: {
        "id": "test-id",
        "created_at": "2026-01-01T00:00:00"
    }[k]
    mock_conn.fetchrow = AsyncMock(return_value=mock_row)
    mock_conn.close = AsyncMock()

    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        resp = client.post("/api/telemetry", json={
            "agent_id": "test-agent",
            "event_type": "tool_called",
            "tool_name": "Bash",
            "escalated": False,
        })
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert "created_at" in data


def test_telemetry__post__with_escalation_flag(client):
    """Test POST /api/telemetry records escalation flag correctly."""
    mock_conn = AsyncMock()
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda s, k: {
        "id": "esc-id",
        "created_at": "2026-01-01T00:00:00"
    }[k]
    mock_conn.fetchrow = AsyncMock(return_value=mock_row)
    mock_conn.close = AsyncMock()

    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        resp = client.post("/api/telemetry", json={
            "agent_id": "orchestrator",
            "event_type": "escalation",
            "escalated": True,
        })
    assert resp.status_code == 201
    assert "id" in resp.json()
