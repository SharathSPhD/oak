"""Unit tests for RoutingStrategy subclasses."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "oak_mcp" / "oak-api-proxy"))
import pytest
from strategies import PassthroughStrategy, StallDetectionStrategy, ConfidenceThresholdStrategy

@pytest.mark.asyncio
async def test_passthrough_strategy__any_input__returns_false():
    s = PassthroughStrategy()
    assert await s.should_escalate({}, {}) is False
    assert await s.should_escalate({"x": 1}, {"content": [{"text": "hi"}]}) is False

@pytest.mark.asyncio
async def test_stall_strategy__empty_response__escalates():
    s = StallDetectionStrategy(min_tokens=20, stall_phrases=[])
    assert await s.should_escalate({}, {"content": [{"text": ""}]}) is True

@pytest.mark.asyncio
async def test_stall_strategy__short_response__escalates():
    s = StallDetectionStrategy(min_tokens=20, stall_phrases=[])
    assert await s.should_escalate({}, {"content": [{"text": "just three words"}]}) is True

@pytest.mark.asyncio
async def test_stall_strategy__stall_phrase__escalates():
    s = StallDetectionStrategy(min_tokens=5, stall_phrases=["i cannot"])
    assert await s.should_escalate({}, {"content": [{"text": "i cannot do this"}]}) is True

@pytest.mark.asyncio
async def test_stall_strategy__normal_response__does_not_escalate():
    s = StallDetectionStrategy(min_tokens=5, stall_phrases=["i cannot"])
    long = "this is a completely normal response with many words and no stall triggers"
    assert await s.should_escalate({}, {"content": [{"text": long}]}) is False

@pytest.mark.asyncio
async def test_confidence_strategy__below_threshold__escalates():
    s = ConfidenceThresholdStrategy(threshold=0.8)
    assert await s.should_escalate({}, {"confidence": 0.3}) is True

@pytest.mark.asyncio
async def test_confidence_strategy__above_threshold__does_not_escalate():
    s = ConfidenceThresholdStrategy(threshold=0.8)
    assert await s.should_escalate({}, {"confidence": 0.9}) is False

@pytest.mark.asyncio
async def test_confidence_strategy__missing_key__does_not_escalate():
    s = ConfidenceThresholdStrategy(threshold=0.8)
    assert await s.should_escalate({}, {}) is False
