"""Unit tests for WebSocket stream endpoint."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import WebSocketDisconnect

from api.main import app

client = TestClient(app)


def test_ws_stream__accepts_connection__and_disconnects_cleanly() -> None:
    """WebSocket accepts connection and handles disconnect cleanly."""
    with patch("api.ws.stream.aioredis.from_url") as mock_from_url:
        mock_redis = AsyncMock()
        mock_pubsub = AsyncMock()
        mock_from_url.return_value = mock_redis
        mock_redis.pubsub.return_value = mock_pubsub

        # Simulate no messages and then disconnect
        mock_pubsub.get_message.return_value = None
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.aclose = AsyncMock()
        mock_redis.aclose = AsyncMock()

        with client.websocket_connect("/ws/test-uuid") as ws:
            # Connection accepted, now close
            pass

        # Verify cleanup was called
        assert mock_pubsub.unsubscribe.called
        assert mock_pubsub.aclose.called
        assert mock_redis.aclose.called


def test_ws_stream__forwards_redis_message_to_client() -> None:
    """WebSocket forwards Redis messages to connected client."""
    with patch("api.ws.stream.aioredis.from_url") as mock_from_url:
        mock_redis = AsyncMock()
        mock_pubsub = AsyncMock()
        mock_from_url.return_value = mock_redis
        mock_redis.pubsub.return_value = mock_pubsub

        # Simulate one message, then None on next call
        test_message = {
            "type": "message",
            "data": '{"agent_id": "agent-1", "event": "task_complete"}',
        }
        mock_pubsub.get_message.side_effect = [test_message, None]
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.aclose = AsyncMock()
        mock_redis.aclose = AsyncMock()

        with client.websocket_connect("/ws/test-uuid") as ws:
            data = ws.receive_text()
            assert data == '{"agent_id": "agent-1", "event": "task_complete"}'


def test_ws_stream__subscribes_to_correct_channel() -> None:
    """WebSocket subscribes to correct Redis channel."""
    with patch("api.ws.stream.aioredis.from_url") as mock_from_url:
        mock_redis = AsyncMock()
        mock_pubsub = AsyncMock()
        mock_from_url.return_value = mock_redis
        mock_redis.pubsub.return_value = mock_pubsub

        mock_pubsub.get_message.return_value = None
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.aclose = AsyncMock()
        mock_redis.aclose = AsyncMock()

        with client.websocket_connect("/ws/problem-uuid-123") as ws:
            pass

        mock_pubsub.subscribe.assert_called_once_with("oak:stream:problem-uuid-123")


def test_ws_stream__handles_redis_unavailable__disconnects_cleanly() -> None:
    """WebSocket disconnects cleanly if Redis connection fails."""
    with patch("api.ws.stream.aioredis.from_url") as mock_from_url:
        mock_from_url.side_effect = ConnectionError("Redis unavailable")

        with pytest.raises(Exception):
            with client.websocket_connect("/ws/test-uuid") as ws:
                pass


def test_ws_stream__sends_heartbeat_on_empty_queue() -> None:
    """WebSocket processes empty messages (heartbeat) without crashing."""
    with patch("api.ws.stream.aioredis.from_url") as mock_from_url:
        mock_redis = AsyncMock()
        mock_pubsub = AsyncMock()
        mock_from_url.return_value = mock_redis
        mock_redis.pubsub.return_value = mock_pubsub

        # Return None multiple times to simulate heartbeat cycles
        mock_pubsub.get_message.side_effect = [None, None, None, None]
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.aclose = AsyncMock()
        mock_redis.aclose = AsyncMock()

        with client.websocket_connect("/ws/test-uuid") as ws:
            # Connection stays open, heartbeat cycles happen in background
            pass

        # Verify pubsub was called for subscription
        assert mock_pubsub.subscribe.called
