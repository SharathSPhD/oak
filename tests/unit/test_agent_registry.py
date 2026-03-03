"""Unit tests for AgentRegistry."""
import json
import sys
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture
def mock_redis():
    # Mock redis.asyncio module
    mock_aioredis = MagicMock()
    mock_r = AsyncMock()
    mock_aioredis.from_url.return_value = mock_r
    
    with patch.dict(sys.modules, {"redis.asyncio": mock_aioredis}):
        with patch("api.services.agent_registry._REDIS_AVAILABLE", True):
            with patch("api.services.agent_registry.aioredis", mock_aioredis):
                yield mock_r


@pytest.mark.asyncio
async def test_agent_registry__register__stores_json_in_redis(mock_redis):
    from api.services.agent_registry import AgentRegistry
    reg = AgentRegistry("redis://localhost:6379")
    await reg.register("agent-1", "data-engineer", "prob-001")
    mock_redis.set.assert_called_once()
    call_args = mock_redis.set.call_args
    assert "oak:agent:agent-1" in str(call_args)


@pytest.mark.asyncio
async def test_agent_registry__update_status__changes_status_field(mock_redis):
    from api.services.agent_registry import AgentRegistry
    reg = AgentRegistry("redis://localhost:6379")
    existing = json.dumps({"agent_id": "a1", "role": "de", "status": "running",
                           "problem_uuid": "", "container_id": "", "last_seen": 1000.0})
    mock_redis.get.return_value = existing
    await reg.update_status("a1", "terminated")
    mock_redis.set.assert_called_once()
    stored = json.loads(mock_redis.set.call_args[0][1])
    assert stored["status"] == "terminated"


@pytest.mark.asyncio
async def test_agent_registry__get_all__returns_agents(mock_redis):
    from api.services.agent_registry import AgentRegistry
    reg = AgentRegistry("redis://localhost:6379")
    mock_redis.keys.return_value = ["oak:agent:a1"]
    mock_redis.get.return_value = json.dumps({"agent_id": "a1", "role": "de",
        "status": "running", "problem_uuid": "p1", "container_id": "", "last_seen": 1.0})
    result = await reg.get_all()
    assert len(result) == 1
    assert result[0].agent_id == "a1"


@pytest.mark.asyncio
async def test_agent_registry__touch__updates_last_seen(mock_redis):
    from api.services.agent_registry import AgentRegistry
    reg = AgentRegistry("redis://localhost:6379")
    old_ts = 1000.0
    existing = json.dumps({"agent_id": "a1", "role": "de", "status": "running",
                           "problem_uuid": "", "container_id": "", "last_seen": old_ts})
    mock_redis.get.return_value = existing
    await reg.touch("a1")
    stored = json.loads(mock_redis.set.call_args[0][1])
    assert stored["last_seen"] > old_ts
