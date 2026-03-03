"""Tests for proxy escalation telemetry logging."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../oak_mcp/oak-api-proxy"))

import pytest
from unittest.mock import patch, MagicMock, call
from main import _log_escalation


def test_log_escalation__increments_global_counter():
    mock_redis = MagicMock()
    with patch("main._redis_sync.from_url", return_value=mock_redis):
        _log_escalation(None)
    mock_redis.incr.assert_called_once_with("oak:telemetry:escalations")


def test_log_escalation__with_problem_uuid__increments_problem_counter():
    mock_redis = MagicMock()
    with patch("main._redis_sync.from_url", return_value=mock_redis):
        _log_escalation("test-prob-001")
    mock_redis.hincrby.assert_called_once_with(
        "oak:telemetry:problem:test-prob-001", "escalations", 1
    )


def test_log_escalation__redis_down__does_not_raise():
    with patch("main._redis_sync.from_url", side_effect=Exception("Redis down")):
        # Must not raise
        _log_escalation("test-prob-001")
