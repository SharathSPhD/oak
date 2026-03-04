__pattern__ = "TemplateMethod"

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class AgentContext:
    """Immutable input to an agent session."""
    agent_id: str
    problem_uuid: str
    role: str
    model: str = "qwen3-coder"


@dataclass
class AgentState:
    """Mutable state restored from Redis at session start."""
    agent_id: str
    keys: dict[str, str] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Output of a completed agent lifecycle."""
    verdict: str          # "pass" | "fail"
    output_path: str      # path to solution artefacts
    error: str = ""       # non-empty if verdict == "fail"


class AgentLifecycle(ABC):
    """
    Template Method: defines the fixed 8-step OAK agent lifecycle.

    Subclasses implement role-specific steps; run() enforces the
    invariant ordering: RESTORE → ORIENT → SKILL_QUERY → EXECUTE
    → VALIDATE → REPORT → CLOSE → SAVE.
    """

    async def run(self, context: AgentContext) -> AgentResult:
        """Template method — fixed lifecycle. Do not override."""
        state = await self.restore(context)
        problem = await self.orient(state)
        skills = await self.skill_query(problem)
        output = await self.execute(problem, skills)
        verdict = await self.validate(output)
        await self.report(verdict)
        await self.close(state)
        await self.save(state, verdict)
        return verdict

    @abstractmethod
    async def restore(self, context: AgentContext) -> AgentState:
        """RESTORE: Load prior session state from Redis working memory."""

    @abstractmethod
    async def orient(self, state: AgentState) -> dict[str, object]:
        """ORIENT: Read PROBLEM.md, claim task from tasks table, understand scope."""

    @abstractmethod
    async def skill_query(self, problem: dict[str, object]) -> list[dict[str, object]]:
        """SKILL_QUERY: Query oak-skills MCP for reusable patterns before writing code."""

    @abstractmethod
    async def execute(
        self, problem: dict[str, object], skills: list[dict[str, object]]
    ) -> dict[str, object]:
        """EXECUTE: Role-specific work (ETL, analysis, ML, synthesis, judgement)."""

    @abstractmethod
    async def validate(self, output: dict[str, object]) -> AgentResult:
        """VALIDATE: Verify output quality; Judge runs pytest; others do self-check."""

    @abstractmethod
    async def report(self, result: AgentResult) -> None:
        """REPORT: Post result summary to mailbox; update task state to COMPLETED."""

    @abstractmethod
    async def close(self, state: AgentState) -> None:
        """CLOSE: Release resources; deregister from AgentRegistry."""

    @abstractmethod
    async def save(self, state: AgentState, result: AgentResult) -> None:
        """SAVE: Persist episodic memory fragment for future skill extraction."""
