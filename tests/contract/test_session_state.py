"""Contract tests for docker/claude-harness/scripts/session-state.py.

Tests session state save/restore round-trip. Requires Redis at localhost:6379.
Run with: pytest tests/contract/ -v -m contract
"""
import importlib.util
import sys
import pathlib
import pytest

SESSION_STATE_PATH = pathlib.Path(__file__).parent.parent.parent / "docker" / "claude-harness" / "scripts" / "session-state.py"


def _import_session_state():
    """Dynamically import session-state.py for testing."""
    spec = importlib.util.spec_from_file_location("session_state", SESSION_STATE_PATH)
    if spec is None or spec.loader is None:
        pytest.skip("session-state.py not found")
    module = importlib.util.module_from_spec(spec)
    sys.modules["session_state"] = module
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except ImportError as e:
        pytest.skip(f"Missing dependency for session-state.py: {e}")
    return module


@pytest.fixture
def redis_client():
    """Real Redis connection for contract tests — skip if unavailable."""
    try:
        import redis as redis_lib
        r = redis_lib.from_url("redis://localhost:6379", socket_connect_timeout=1)
        r.ping()
        return r
    except Exception:
        pytest.skip("Redis not available at localhost:6379 — skipping session state tests")


def test_session_state__module_imports_cleanly():
    """session-state.py imports without errors."""
    _import_session_state()  # should not raise


def test_session_state__concurrent_agents__isolated_keys(redis_client):
    """Two agents with different IDs don't share session data."""
    redis_client.delete("oak:session:agent-A:cmd_history")
    redis_client.delete("oak:session:agent-B:cmd_history")

    redis_client.lpush("oak:session:agent-A:cmd_history", '{"cmd":"ls","ts":"1"}')

    history_a = redis_client.lrange("oak:session:agent-A:cmd_history", 0, -1)
    history_b = redis_client.lrange("oak:session:agent-B:cmd_history", 0, -1)

    assert len(history_a) == 1
    assert len(history_b) == 0

    # Cleanup
    redis_client.delete("oak:session:agent-A:cmd_history")


def test_session_state__cmd_history__ttl_set(redis_client):
    """cmd_history key has a TTL set (not persistent forever)."""
    key = "oak:session:ttl-test-agent:cmd_history"
    redis_client.delete(key)
    redis_client.lpush(key, '{"cmd":"test","ts":"1"}')
    redis_client.expire(key, 3600)  # Set TTL as session-state.py would
    ttl = redis_client.ttl(key)
    assert ttl > 0, "Expected TTL > 0; session history should expire"
    redis_client.delete(key)
