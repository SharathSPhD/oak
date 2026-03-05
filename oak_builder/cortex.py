"""Cortex — the brain of the OAK autonomous builder.

Replaces the fixed-sprint loop with a perception-decision-action cognitive loop.
"""
from __future__ import annotations

__pattern__ = "TemplateMethod"

import asyncio
import json
import logging
import os
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

logger = logging.getLogger("oak.builder.cortex")

DEFAULT_CORTEX_STATE_PATH = "/workspaces/builder/cortex_state.json"
DEFAULT_THOUGHTS_LOG_PATH = "/workspaces/builder/thoughts.log"
REST_SECONDS = int(os.environ.get("OAK_BUILDER_REST_SECONDS", "900"))
FAILURE_COOLDOWN_CYCLES = 3
RESOURCE_PRESSURE_CPU_PCT = 90.0
RESOURCE_PRESSURE_MEM_PCT = 85.0


@dataclass
class CortexState:
    """Persisted state for the cognitive loop."""

    cycle_count: int = 0
    last_action: str = ""
    last_action_result: str = ""
    last_action_time: str = ""
    pending_research: list[str] = field(default_factory=list)
    recent_failures: list[dict] = field(default_factory=list)
    recent_successes: list[dict] = field(default_factory=list)
    model_benchmarks: dict = field(default_factory=dict)
    domain_coverage: dict = field(default_factory=dict)
    manifest_delta: list[str] = field(default_factory=list)
    active_branch: str = ""
    version: int = 1

    def to_dict(self) -> dict:
        return {
            "cycle_count": self.cycle_count,
            "last_action": self.last_action,
            "last_action_result": self.last_action_result,
            "last_action_time": self.last_action_time,
            "pending_research": self.pending_research,
            "recent_failures": self.recent_failures[-20:],
            "recent_successes": self.recent_successes[-20:],
            "model_benchmarks": self.model_benchmarks,
            "domain_coverage": self.domain_coverage,
            "manifest_delta": self.manifest_delta,
            "active_branch": self.active_branch,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CortexState:
        return cls(
            cycle_count=data.get("cycle_count", 0),
            last_action=data.get("last_action", ""),
            last_action_result=data.get("last_action_result", ""),
            last_action_time=data.get("last_action_time", ""),
            pending_research=data.get("pending_research", []),
            recent_failures=data.get("recent_failures", [])[-20:],
            recent_successes=data.get("recent_successes", [])[-20:],
            model_benchmarks=data.get("model_benchmarks", {}),
            domain_coverage=data.get("domain_coverage", {}),
            manifest_delta=data.get("manifest_delta", []),
            active_branch=data.get("active_branch", ""),
            version=data.get("version", 1),
        )


@dataclass
class Perception:
    """Transient snapshot of current state for decision-making."""

    telemetry: dict = field(default_factory=dict)
    skill_gaps: list[dict] = field(default_factory=list)
    failed_problems: list[dict] = field(default_factory=list)
    completed_problems: list[dict] = field(default_factory=list)
    available_models: list[str] = field(default_factory=list)
    resource_usage: dict = field(default_factory=dict)
    user_problems_active: bool = False
    circuit_breaker_state: str = "closed"
    sprint_history: list[dict] = field(default_factory=list)
    manifest_targets: list[str] = field(default_factory=list)


@dataclass
class ActionResult:
    """Result of executing an action."""

    success: bool
    summary: str
    artifacts: dict = field(default_factory=dict)


class Action(ABC):
    """Base class for Cortex actions."""

    name: str = ""
    category: str = ""

    def __init__(self, *, api_url: str = "", ollama_url: str = "") -> None:
        self.api_url = api_url
        self.ollama_url = ollama_url

    @abstractmethod
    async def estimate_value(
        self, state: CortexState, perception: Perception
    ) -> float:
        """0.0 = no value right now, 1.0 = highest possible value."""

    @abstractmethod
    async def execute(self, state: CortexState) -> ActionResult:
        """Execute the action and return the result."""


class Cortex:
    """The brain of the autonomous builder — perception-decision-action loop."""

    def __init__(
        self,
        api_url: str,
        ollama_url: str,
        *,
        state_path: str | None = None,
        thoughts_log_path: str | None = None,
        manifest_domains_path: str | None = None,
        ollama_container: str | None = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.ollama_url = ollama_url.rstrip("/")
        self.state_path = Path(
            state_path
            or os.environ.get("OAK_CORTEX_STATE_PATH", DEFAULT_CORTEX_STATE_PATH)
        )
        self.thoughts_log = Path(
            thoughts_log_path
            or os.environ.get(
                "OAK_CORTEX_THOUGHTS_LOG",
                DEFAULT_THOUGHTS_LOG_PATH,
            )
        )
        self.manifest_domains_path = Path(
            manifest_domains_path or "/oak-repo/manifest_domains.json"
        )
        self.ollama_container = ollama_container or "oak-ollama"

        self.state = self._load_state()
        self.actions: dict[str, Action] = {}

    def register_action(self, action: Action) -> None:
        """Register an action for the decision loop."""
        if action.name:
            self.actions[action.name] = action
            logger.debug("Registered action: %s (%s)", action.name, action.category)

    async def run(self) -> None:
        """Main cognitive loop — runs forever."""
        await self._wait_for_api()
        while True:
            try:
                if self._should_rest():
                    self._think("Resting — resource pressure or cooldown")
                    await asyncio.sleep(REST_SECONDS)
                    continue

                perception = await self.perceive()

                if perception.user_problems_active:
                    self._think("User problems active — deferring all actions")
                    await asyncio.sleep(30)
                    continue

                action_name = await self.reflect_and_decide(perception)

                if action_name:
                    result = await self.act(action_name, perception)
                    await self.learn(action_name, result)
                else:
                    self._think("No high-value action — resting")
                    await asyncio.sleep(REST_SECONDS)
                    continue

                self.state.cycle_count += 1
                self._save_state()

            except Exception as exc:
                logger.exception("Cortex loop error: %s", exc)
                self._think(f"Loop error (recovering): {exc}")
                await asyncio.sleep(60)

    async def perceive(self) -> Perception:
        """Read all signals: telemetry, skills, verdicts, models, resources, manifest."""
        perception = Perception()

        async with httpx.AsyncClient(base_url=self.api_url, timeout=15) as client:
            # Telemetry
            try:
                resp = await client.get("/api/telemetry")
                if resp.status_code == 200:
                    perception.telemetry = resp.json()
            except httpx.HTTPError as exc:
                logger.warning("Could not fetch telemetry: %s", exc)

            # Problems (failed vs completed)
            try:
                resp = await client.get("/api/problems")
                if resp.status_code == 200:
                    data = resp.json()
                    problems = data if isinstance(data, list) else []
                    perception.failed_problems = [
                        p for p in problems if p.get("status") == "failed"
                    ]
                    perception.completed_problems = [
                        p for p in problems if p.get("status") == "complete"
                    ]
                    perception.user_problems_active = any(
                        p.get("status") in ("active", "assembling")
                        and p.get("source", "user") != "self-build"
                        for p in problems
                    )
            except httpx.HTTPError as exc:
                logger.warning("Could not fetch problems: %s", exc)

            # Health (circuit breaker / system state)
            try:
                resp = await client.get("/health")
                if resp.status_code == 200:
                    health = resp.json()
                    perception.circuit_breaker_state = health.get(
                        "circuit_breaker", "closed"
                    )
            except httpx.HTTPError:
                pass

        # Skills / gap analysis via manifest
        perception.skill_gaps = await self._compute_skill_gaps()

        # Available models (Ollama)
        perception.available_models = await self._fetch_available_models()

        # Resource usage
        perception.resource_usage = self._get_resource_usage()

        # Sprint history from state
        perception.sprint_history = (
            self.state.recent_successes[-10:] + self.state.recent_failures[-10:]
        )

        # Manifest targets
        perception.manifest_targets = self.state.manifest_delta or []

        return perception

    async def _compute_skill_gaps(self) -> list[dict]:
        """Compute skill gaps from manifest_domains.json and API skills."""
        gaps: list[dict] = []
        if not self.manifest_domains_path.exists():
            return gaps

        try:
            manifest = json.loads(self.manifest_domains_path.read_text())
            domains = manifest.get("domains", [])
            floor = manifest.get("floor_permanent_skills_per_domain", 3)

            async with httpx.AsyncClient(
                base_url=self.api_url, timeout=10
            ) as client:
                for domain in domains:
                    domain_id = domain.get("id", "")
                    category = domain.get("skill_category", domain_id)
                    permanent_count = 0
                    try:
                        resp = await client.get(
                            "/api/skills",
                            params={
                                "status": "permanent",
                                "category": category,
                                "top_k": 50,
                            },
                        )
                        if resp.status_code == 200:
                            skills = resp.json()
                            permanent_count = (
                                len(skills) if isinstance(skills, list) else 0
                            )
                    except httpx.HTTPError:
                        pass

                    if permanent_count < floor:
                        gaps.append({
                            "domain_id": domain_id,
                            "domain_name": domain.get("name", domain_id),
                            "permanent_count": permanent_count,
                            "floor": floor,
                            "gap_score": (floor - permanent_count) / floor,
                        })
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not compute skill gaps: %s", exc)

        return gaps

    async def _fetch_available_models(self) -> list[str]:
        """Fetch available Ollama models via HTTP or docker exec."""
        # Try OpenAI-compatible /v1/models first (proxy)
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.ollama_url}/v1/models")
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("data", [])
                    return [m.get("id", "") for m in models if m]
        except httpx.HTTPError:
            pass

        # Try Ollama native /api/tags
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.ollama_url}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("models", [])
                    return [m.get("name", "") for m in models if m.get("name")]
        except httpx.HTTPError:
            pass

        # Fallback: docker exec ollama list
        try:
            result = subprocess.run(
                ["docker", "exec", self.ollama_container, "ollama", "list"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")[1:]
                return [
                    line.split()[0]
                    for line in lines
                    if line.strip()
                ]
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass

        return []

    def _get_resource_usage(self) -> dict:
        """Get CPU and memory usage via /proc or psutil."""
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory().percent
            return {"cpu_pct": cpu, "memory_pct": mem}
        except ImportError:
            pass

        # Fallback: /proc
        try:
            with open("/proc/meminfo") as f:
                lines = f.read()
            total = 0
            avail = 0
            for line in lines.split("\n"):
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    avail = int(line.split()[1])
            if total > 0:
                mem_pct = 100.0 * (1 - avail / total)
                return {"cpu_pct": 0.0, "memory_pct": round(mem_pct, 1)}
        except OSError:
            pass

        return {"cpu_pct": 0.0, "memory_pct": 0.0}

    async def reflect_and_decide(self, p: Perception) -> str | None:
        """Use LLM to reason about what action to take next."""
        if not self.actions:
            self._think("No actions registered — cannot decide")
            return None

        # Build context for the LLM
        context = self._build_perception_summary(p)
        actions_list = "\n".join(
            f"- {name} ({a.category})" for name, a in self.actions.items()
        )

        prompt = f"""You are the OAK autonomous builder's decision engine.
Given the current perception, choose the single best action to execute next,
or respond with "rest" if no action has sufficient value.

Current state:
{context}

Available actions:
{actions_list}

Respond with ONLY the action name (exactly as listed) or "rest". No explanation."""

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.ollama_url}/v1/chat/completions",
                    json={
                        "model": "qwen3-coder",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 50,
                        "temperature": 0.2,
                    },
                )
                if resp.status_code != 200:
                    self._think(f"Ollama returned {resp.status_code}")
                    return None

                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    return None

                content = (
                    choices[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                    .lower()
                )

                self._think(f"LLM chose: {content}")

                if content == "rest" or not content:
                    return None

                # Match to registered action (case-insensitive)
                for name in self.actions:
                    if name.lower() in content or content in name.lower():
                        return name

                # Exact match
                if content in self.actions:
                    return content

                return None

        except httpx.HTTPError as exc:
            logger.warning("Ollama request failed: %s", exc)
            self._think(f"Ollama failed: {exc}")
            return None

    def _build_perception_summary(self, p: Perception) -> str:
        """Build a concise text summary of perception for the LLM."""
        last_result = ""
        if self.state.last_action_result:
            last_result = f" ({self.state.last_action_result[:80]}...)"
        parts = [
            f"Cycle: {self.state.cycle_count}",
            f"Last action: {self.state.last_action or 'none'}{last_result}",
            f"Skill gaps: {len(p.skill_gaps)}",
            f"Failed problems: {len(p.failed_problems)}",
            f"Completed problems: {len(p.completed_problems)}",
            f"Available models: {len(p.available_models)}",
            f"Circuit breaker: {p.circuit_breaker_state}",
            f"Recent failures: {len(self.state.recent_failures)}",
            f"Recent successes: {len(self.state.recent_successes)}",
        ]
        if p.resource_usage:
            parts.append(
                f"Resource: CPU {p.resource_usage.get('cpu_pct', 0)}%, "
                f"Mem {p.resource_usage.get('memory_pct', 0)}%"
            )
        if p.skill_gaps:
            parts.append(
                "Top gaps: " + ", ".join(
                    g["domain_name"] for g in p.skill_gaps[:3]
                )
            )
        return "\n".join(parts)

    async def act(
        self, action_name: str, perception: Perception
    ) -> ActionResult:
        """Execute the chosen action."""
        action = self.actions.get(action_name)
        if not action:
            self._think(f"Unknown action: {action_name}")
            return ActionResult(success=False, summary=f"Unknown action: {action_name}")

        self._think(f"Executing: {action_name}")
        try:
            result = await action.execute(self.state)
            self._think(f"Result: {result.summary}")
            return result
        except Exception as e:
            logger.exception("Action %s failed", action_name)
            self._think(f"Action {action_name} failed: {e}")
            return ActionResult(success=False, summary=str(e))

    async def learn(self, action_name: str, result: ActionResult) -> None:
        """Store episode, update state, feed back."""
        episode = {
            "cycle": self.state.cycle_count,
            "action": action_name,
            "success": result.success,
            "summary": result.summary[:200],
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if result.success:
            self.state.recent_successes.append(episode)
            self.state.recent_successes = self.state.recent_successes[-20:]
        else:
            self.state.recent_failures.append(episode)
            self.state.recent_failures = self.state.recent_failures[-20:]

        self.state.last_action = action_name
        self.state.last_action_result = result.summary[:200]
        self.state.last_action_time = datetime.now(UTC).isoformat()

        # POST to /api/telemetry if endpoint exists
        try:
            async with httpx.AsyncClient(
                base_url=self.api_url, timeout=5
            ) as client:
                await client.post(
                    "/api/telemetry",
                    json={
                        "problem_id": None,
                        "agent_id": "cortex",
                        "event_type": f"cortex_{action_name}",
                        "tool_name": "cortex_learn",
                        "tool_input": {"success": result.success},
                        "tool_response": {"summary": result.summary[:500]},
                        "duration_ms": 0,
                        "escalated": False,
                    },
                )
        except (httpx.HTTPError, Exception):
            pass

    def _think(self, thought: str) -> None:
        """Log a thought with timestamp."""
        line = f"[{datetime.now(UTC).isoformat()}] {thought}\n"
        try:
            self.thoughts_log.parent.mkdir(parents=True, exist_ok=True)
            with open(self.thoughts_log, "a") as f:
                f.write(line)
        except OSError as exc:
            logger.debug("Could not write thoughts log: %s", exc)
        logger.info("THOUGHT: %s", thought)

    def _load_state(self) -> CortexState:
        """Load persisted state from disk."""
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text())
                return CortexState.from_dict(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not load cortex state: %s", exc)
        return CortexState()

    def _save_state(self) -> None:
        """Persist state to disk."""
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(
                json.dumps(self.state.to_dict(), indent=2)
            )
        except OSError as exc:
            logger.warning("Could not save cortex state: %s", exc)

    def _should_rest(self) -> bool:
        """Return True if we should rest (resource pressure, cooldown)."""
        # Recent failure cooldown
        if self.state.recent_failures:
            last_fail = self.state.recent_failures[-1]
            fail_cycle = last_fail.get("cycle", 0)
            if self.state.cycle_count - fail_cycle < FAILURE_COOLDOWN_CYCLES:
                return True

        # Resource pressure
        usage = self._get_resource_usage()
        cpu = usage.get("cpu_pct", 0)
        mem = usage.get("memory_pct", 0)
        if cpu >= RESOURCE_PRESSURE_CPU_PCT or mem >= RESOURCE_PRESSURE_MEM_PCT:
            return True

        return False

    async def _wait_for_api(self) -> None:
        """Wait until oak-api is healthy before starting the loop."""
        logger.info("Waiting for oak-api at %s...", self.api_url)
        for _attempt in range(60):
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    resp = await client.get(f"{self.api_url}/health")
                    if resp.status_code == 200:
                        logger.info("oak-api is healthy")
                        return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(5)
        logger.error("oak-api not available after 5 minutes, starting anyway")
