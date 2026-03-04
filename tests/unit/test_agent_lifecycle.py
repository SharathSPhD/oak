"""Unit tests for AgentLifecycle TemplateMethod pattern."""
import pytest
from unittest.mock import AsyncMock, call, MagicMock
from api.lifecycle.agent_lifecycle import AgentLifecycle, AgentContext, AgentResult, AgentState


class ConcreteAgent(AgentLifecycle):
    """Minimal concrete implementation for testing."""
    def __init__(self, mock_calls: list) -> None:
        self._calls = mock_calls

    async def restore(self, context: AgentContext) -> AgentState:
        self._calls.append("restore")
        return AgentState(agent_id=context.agent_id)

    async def orient(self, state: AgentState) -> dict:
        self._calls.append("orient")
        return {"problem": "test"}

    async def skill_query(self, problem: dict) -> list:
        self._calls.append("skill_query")
        return []

    async def execute(self, problem: dict, skills: list) -> dict:
        self._calls.append("execute")
        return {"output": "done"}

    async def validate(self, output: dict) -> AgentResult:
        self._calls.append("validate")
        return AgentResult(verdict="pass", output_path="/workspace/out")

    async def report(self, result: AgentResult) -> None:
        self._calls.append("report")

    async def close(self, state: AgentState) -> None:
        self._calls.append("close")

    async def save(self, state: AgentState, result: AgentResult) -> None:
        self._calls.append("save")


@pytest.mark.asyncio
async def test_agent_lifecycle__run__enforces_fixed_step_order():
    calls = []
    agent = ConcreteAgent(calls)
    ctx = AgentContext(agent_id="a1", problem_uuid="p1", role="orchestrator")
    result = await agent.run(ctx)
    assert calls == ["restore", "orient", "skill_query", "execute", "validate", "report", "close", "save"]


@pytest.mark.asyncio
async def test_agent_lifecycle__run__returns_agent_result():
    agent = ConcreteAgent([])
    ctx = AgentContext(agent_id="a1", problem_uuid="p1", role="orchestrator")
    result = await agent.run(ctx)
    assert isinstance(result, AgentResult)
    assert result.verdict == "pass"


def test_agent_lifecycle__abstract__cannot_instantiate_directly():
    with pytest.raises(TypeError):
        AgentLifecycle()  # type: ignore[abstract]


def test_agent_context__defaults():
    ctx = AgentContext(agent_id="a", problem_uuid="p", role="judge")
    assert ctx.model == "qwen3-coder"


def test_agent_result__fail_has_error():
    r = AgentResult(verdict="fail", output_path="", error="Judge FAIL: 3 tests failed")
    assert r.error != ""
