__pattern__ = "ChainOfResponsibility"

from abc import ABC, abstractmethod
from dataclasses import dataclass
import pathlib
import re

from api.config import settings


@dataclass
class ToolCall:
    command: str
    agent_id: str
    problem_uuid: str


@dataclass
class ValidationResult:
    allowed: bool
    reason: str


class ToolValidator(ABC):
    """Abstract handler in the Chain of Responsibility."""

    def __init__(self) -> None:
        self._next: ToolValidator | None = None

    def set_next(self, handler: "ToolValidator") -> "ToolValidator":
        self._next = handler
        return handler

    async def validate(self, call: ToolCall) -> ValidationResult:
        result = await self._check(call)
        if not result.allowed:
            return result
        if self._next:
            return await self._next.validate(call)
        return ValidationResult(allowed=True, reason="all checks passed")

    @abstractmethod
    async def _check(self, call: ToolCall) -> ValidationResult: ...


def _load_patterns(prefix_filter: str | None = None) -> list[str]:
    """Load patterns from scripts/deny-patterns.txt."""
    deny_file = pathlib.Path(__file__).parent.parent / "scripts" / "deny-patterns.txt"
    patterns: list[str] = []
    for line in deny_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if prefix_filter is None:
            if not line.startswith("OAK:"):
                patterns.append(line)
        else:
            if line.startswith(prefix_filter):
                patterns.append(line[len(prefix_filter):].strip())
    return patterns


class HardDenyListValidator(ToolValidator):
    """Layer 1: system-destruction and shell-injection patterns from deny-patterns.txt."""

    async def _check(self, call: ToolCall) -> ValidationResult:
        for pattern in _load_patterns(prefix_filter=None):
            if re.search(pattern, call.command, re.IGNORECASE):
                return ValidationResult(
                    allowed=False,
                    reason=f"Blocked by hard deny list pattern: {pattern!r}",
                )
        return ValidationResult(allowed=True, reason="passed hard deny list")


class OAKDenyListValidator(ToolValidator):
    """Layer 2: OAK business-rule patterns (OAK: prefixed lines in deny-patterns.txt)."""

    async def _check(self, call: ToolCall) -> ValidationResult:
        for pattern in _load_patterns(prefix_filter="OAK:"):
            if re.search(pattern, call.command, re.IGNORECASE):
                return ValidationResult(
                    allowed=False,
                    reason=f"Blocked by OAK business rule: {pattern!r}",
                )
        return ValidationResult(allowed=True, reason="passed OAK deny list")


class ResourceCapValidator(ToolValidator):
    """Layer 3: reject tool calls that would exceed configured resource caps."""

    async def _check(self, call: ToolCall) -> ValidationResult:
        # Phase 1 stub: resource cap enforcement requires live agent count from DB.
        # This validator passes through in Phase 0/1; enforced in Phase 2.
        _ = settings  # cap values are settings.max_agents_per_problem etc.
        return ValidationResult(allowed=True, reason="resource cap check passed (Phase 1 stub)")


def build_validation_chain() -> ToolValidator:
    """Construct the default three-layer chain: Hard -> OAK -> ResourceCap."""
    hard = HardDenyListValidator()
    oak = OAKDenyListValidator()
    cap = ResourceCapValidator()
    hard.set_next(oak).set_next(cap)
    return hard
