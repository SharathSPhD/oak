"""Cortex — the brain of the OAK autonomous builder.

Replaces the fixed-sprint loop with a perception-decision-action cognitive loop.
Syncs state to Redis so the API + UI can observe it in real time.
Subscribes to Redis pubsub for pause/resume/start control from the UI.
"""
from __future__ import annotations

__pattern__ = "TemplateMethod"

import asyncio
import json
import logging
import os
import subprocess
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx
import redis.asyncio as aioredis

logger = logging.getLogger("oak.builder.cortex")

DEFAULT_CORTEX_STATE_PATH = "/workspaces/builder/cortex_state.json"
DEFAULT_THOUGHTS_LOG_PATH = "/workspaces/builder/thoughts.log"
REST_SECONDS = int(os.environ.get("OAK_BUILDER_REST_SECONDS", "120"))
FAILURE_COOLDOWN_CYCLES = 1
RESOURCE_PRESSURE_CPU_PCT = 90.0
RESOURCE_PRESSURE_MEM_PCT = 85.0

REDIS_STATE_KEY = "oak:builder:state"
REDIS_HISTORY_KEY = "oak:builder:history"
REDIS_CONTROL_CHANNEL = "oak:builder:control"
REDIS_THOUGHTS_KEY = "oak:builder:thoughts"


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
        redis_url: str | None = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.ollama_url = ollama_url.rstrip("/")
        self.redis_url = redis_url or os.environ.get(
            "OAK_REDIS_URL", "redis://oak-redis:6379/0"
        )
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
        self._paused = False
        self._stopped = False
        self._current_status = "idle"
        self._recent_thoughts: list[str] = []

    def register_action(self, action: Action) -> None:
        """Register an action for the decision loop."""
        if action.name:
            self.actions[action.name] = action
            logger.debug("Registered action: %s (%s)", action.name, action.category)

    async def run(self) -> None:
        """Main cognitive loop — runs until stopped."""
        await self._wait_for_api()
        asyncio.create_task(self._control_listener())
        while not self._stopped:
            try:
                if self._paused:
                    self._set_status("paused")
                    await self._sync_to_redis()
                    await asyncio.sleep(5)
                    continue

                if self._should_rest():
                    self._think("Resting — resource pressure or cooldown")
                    self._set_status("resting")
                    await self._sync_to_redis()
                    await self._interruptible_sleep(REST_SECONDS)
                    continue

                self._set_status("perceiving")
                await self._sync_to_redis()
                perception = await self.perceive()

                if perception.user_problems_active:
                    self._think("User problems active — deferring all actions")
                    self._set_status("deferred")
                    await self._sync_to_redis()
                    await self._interruptible_sleep(30)
                    continue

                self._set_status("deciding")
                await self._sync_to_redis()
                action_name = await self.reflect_and_decide(perception)

                if action_name:
                    self._set_status("running")
                    await self._sync_to_redis()
                    result = await self.act(action_name, perception)
                    await self.learn(action_name, result)
                else:
                    self._think("No high-value action — resting briefly")
                    self._set_status("resting")
                    await self._sync_to_redis()
                    await self._interruptible_sleep(30)
                    continue

                self.state.cycle_count += 1
                self._save_state()
                await self._sync_to_redis()

            except Exception as exc:
                logger.exception("Cortex loop error: %s", exc)
                self._think(f"Loop error (recovering): {exc}")
                self._set_status("error")
                await self._sync_to_redis()
                await self._interruptible_sleep(30)

        self._think("Cortex stopped gracefully — saving state")
        self._set_status("stopped")
        self._save_state()
        await self._sync_to_redis()
        logger.info("Cortex shut down cleanly at cycle %d", self.state.cycle_count)

    def _set_status(self, status: str) -> None:
        self._current_status = status

    async def _interruptible_sleep(self, seconds: int) -> None:
        """Sleep in 5-second chunks, waking early on stop or resume."""
        for _ in range(0, seconds, 5):
            if self._stopped:
                return
            await asyncio.sleep(5)
            if self._stopped:
                return
            if not self._paused and self._current_status == "resting":
                break

    async def _control_listener(self) -> None:
        """Background task: subscribe to Redis pubsub for pause/resume/start."""
        while True:
            try:
                r = aioredis.from_url(self.redis_url, decode_responses=True)
                pubsub = r.pubsub()
                await pubsub.subscribe(REDIS_CONTROL_CHANNEL)
                logger.info("Subscribed to %s", REDIS_CONTROL_CHANNEL)
                async for msg in pubsub.listen():
                    if msg["type"] != "message":
                        continue
                    try:
                        payload = json.loads(msg["data"])
                        action = payload.get("action", "")
                        if action == "pause":
                            self._paused = True
                            self._think("Paused by control channel")
                        elif action in ("resume", "start"):
                            self._paused = False
                            self._think(f"Resumed by control channel ({action})")
                        elif action == "stop":
                            self._stopped = True
                            self._paused = False
                            self._think("Stop requested — shutting down gracefully")
                            logger.info("Stop signal received via control channel")
                            return
                        else:
                            self._think(f"Unknown control action: {action}")
                    except (json.JSONDecodeError, TypeError):
                        pass
            except Exception as exc:
                logger.warning("Control listener error (reconnecting): %s", exc)
                await asyncio.sleep(5)

    async def _sync_to_redis(self) -> None:
        """Write current state + history to Redis so the API/UI can see it."""
        try:
            r = aioredis.from_url(self.redis_url, decode_responses=True)

            consecutive_failures = 0
            for ep in reversed(self.state.recent_failures + self.state.recent_successes):
                if ep.get("success"):
                    break
                consecutive_failures += 1

            state_payload = {
                "status": self._current_status,
                "builder_enabled": True,
                "cycle_count": self.state.cycle_count,
                "last_action": self.state.last_action,
                "last_action_result": self.state.last_action_result,
                "last_action_time": self.state.last_action_time,
                "circuit_breaker": {
                    "state": "halted" if consecutive_failures >= 5 else "closed",
                    "consecutive_failures": consecutive_failures,
                },
                "current_sprint": {
                    "cycle": self.state.cycle_count,
                    "action": self.state.last_action,
                } if self._current_status == "running" else None,
                "last_sprint_result": self._last_sprint_result(),
                "thoughts": self._recent_thoughts[-10:],
            }
            await r.set(REDIS_STATE_KEY, json.dumps(state_payload), ex=300)

            sprints = []
            all_episodes = sorted(
                self.state.recent_successes + self.state.recent_failures,
                key=lambda e: e.get("cycle", 0),
            )
            for ep in all_episodes:
                sprints.append({
                    "sprint_number": ep.get("cycle", 0),
                    "started_at": ep.get("timestamp", ""),
                    "problems_submitted": 1,
                    "problems_passed": 1 if ep.get("success") else 0,
                    "skills_ingested": ep.get("artifacts", {}).get("skills_ingested", 0)
                    if isinstance(ep.get("artifacts"), dict) else 0,
                    "changes_committed": False,
                    "circuit_breaker_state": "closed",
                    "action": ep.get("action", ""),
                    "summary": ep.get("summary", ""),
                    "success": ep.get("success", False),
                })

            domain_baselines = {}
            try:
                async with httpx.AsyncClient(
                    base_url=self.api_url, timeout=5
                ) as client:
                    for domain in [
                        "sales", "pricing", "marketing", "supply_chain",
                        "customer", "finance", "operations", "human_capital",
                        "product",
                    ]:
                        try:
                            resp = await client.get(
                                "/api/skills",
                                params={"status": "permanent", "category": domain, "top_k": 50},
                            )
                            if resp.status_code == 200:
                                skills = resp.json()
                                count = len(skills) if isinstance(skills, list) else 0
                                domain_baselines[domain] = min(count / 3.0, 1.0)
                            else:
                                domain_baselines[domain] = 0.0
                        except httpx.HTTPError:
                            domain_baselines[domain] = 0.0
            except Exception:
                pass

            skill_count = 0
            try:
                async with httpx.AsyncClient(
                    base_url=self.api_url, timeout=5
                ) as client:
                    resp = await client.get("/api/skills", params={"top_k": 500})
                    if resp.status_code == 200:
                        skills = resp.json()
                        skill_count = len(skills) if isinstance(skills, list) else 0
            except Exception:
                pass

            history_payload = {
                "sprint_count": self.state.cycle_count,
                "total_skills": skill_count,
                "total_commits": 0,
                "release_count": 0,
                "stories_since_release": self.state.cycle_count % 5,
                "domain_baselines": domain_baselines,
                "sprints": sprints[-20:],
            }
            await r.set(REDIS_HISTORY_KEY, json.dumps(history_payload), ex=300)

            if self._recent_thoughts:
                await r.set(
                    REDIS_THOUGHTS_KEY,
                    json.dumps(self._recent_thoughts[-50:]),
                    ex=300,
                )

            await r.aclose()
        except Exception as exc:
            logger.debug("Redis sync failed: %s", exc)

    def _last_sprint_result(self) -> dict | None:
        all_episodes = self.state.recent_successes + self.state.recent_failures
        if not all_episodes:
            return None
        recent = sorted(all_episodes, key=lambda e: e.get("cycle", 0))[-5:]
        passed = sum(1 for e in recent if e.get("success"))
        failed = len(recent) - passed
        return {
            "passed": passed,
            "failed": failed,
            "skills": 0,
            "committed": False,
        }

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
        """Fetch available Ollama models directly (not via proxy)."""
        ollama_direct = os.environ.get("OAK_OLLAMA_DIRECT_URL", "http://oak-ollama:11434")
        # Use Ollama native /api/tags for accurate local model list
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{ollama_direct}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("models", [])
                    return [m.get("name", "") for m in models if m.get("name")]
        except httpx.HTTPError:
            pass

        # Fallback: try proxy but filter out non-local models
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.ollama_url}/v1/models")
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("data", [])
                    return [
                        m.get("id", "") for m in models
                        if m and "claude" not in m.get("id", "").lower()
                    ]
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

        context = self._build_perception_summary(p)

        action_descriptions = {
            "run_domain_problem": "Generate a synthetic dataset for a domain gap, submit it through the pipeline, run specialists and judge",
            "audit_self": "Introspect on recent performance: review success/failure rates, identify patterns, suggest improvements",
            "replay_failure": "Re-examine a recent failure to understand root cause and learn from it",
            "benchmark_regression": "Run canonical benchmark problems to detect quality regressions",
            "web_research": "Search the web for techniques, papers, or tools relevant to current gaps",
            "harvest_huggingface": "Browse HuggingFace for useful models, datasets, or techniques",
            "read_paper": "Read and summarize a research paper relevant to current domain gaps",
            "pull_model": "Download a new Ollama model to expand capabilities",
            "benchmark_models": "Compare available models on quality/speed for different roles",
            "update_routing": "Update model-to-role routing based on benchmark results",
            "improve_prompt": "Refine agent prompts based on failure analysis",
            "improve_harness": "Improve the harness entrypoint script for better specialist execution",
            "fix_bug": "Fix a known bug identified through introspection or failure replay",
            "add_feature": "Add a new capability to the OAK system",
            "open_branch": "Create a git branch for a planned code change",
            "pr_review": "Review pending pull requests",
            "run_acceptance": "Run lint + test acceptance suite",
            "merge_to_main": "Merge an accepted branch to main",
            "push_to_remote": "Push main to the remote repository",
            "rebuild_image": "Rebuild a Docker image after code changes",
            "update_dependency": "Update a Python/system dependency",
            "add_dependency": "Add a new dependency to requirements",
            "build_rag_index": "Build or update the RAG index from domain knowledge",
            "evaluate_rag_quality": "Evaluate RAG retrieval quality",
            "propose_amendment": "Propose a change to the OAK manifest",
            "ratify_amendment": "Approve and apply a proposed manifest change",
            "self_modify": "Full self-modification pipeline: branch, change, test, merge, rebuild, hot-swap",
        }

        actions_list = "\n".join(
            f"- {name} ({a.category}): {action_descriptions.get(name, 'No description')}"
            for name, a in self.actions.items()
        )

        recent_action_counts = Counter(
            e.get("action", "") for e in
            (self.state.recent_successes[-10:] + self.state.recent_failures[-10:])
        )
        diversity_note = ""
        if recent_action_counts:
            most_common = recent_action_counts.most_common(1)[0]
            if most_common[1] >= 3:
                diversity_note = (
                    f"\nIMPORTANT: You have chosen '{most_common[0]}' {most_common[1]} times "
                    f"in the last {sum(recent_action_counts.values())} cycles. "
                    f"Strongly consider a DIFFERENT action for diversity and broader improvement."
                )

        prompt = f"""You are the OAK autonomous builder's strategic decision engine.
Your goal is to make OAK continuously better — not just run domain problems, but also
introspect, audit, pull new models, improve prompts, fix bugs, and self-modify.

Current state:
{context}

Available actions (name, category, description):
{actions_list}
{diversity_note}

Think step by step:
1. What is the most impactful action right now given the current state?
2. Have I been doing the same thing repeatedly? If so, try something different.
3. Are there failures I should diagnose before running more problems?

Respond with your reasoning in 1-2 sentences, then on the LAST LINE write ONLY the action name.
If no action has value, write "rest" on the last line."""

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.ollama_url}/v1/chat/completions",
                    json={
                        "model": "qwen3-coder",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 200,
                        "temperature": 0.4,
                    },
                )
                if resp.status_code != 200:
                    self._think(f"Ollama returned {resp.status_code}")
                    return None

                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    return None

                raw = (
                    choices[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )

                lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
                if not lines:
                    return None

                chosen = lines[-1].lower().strip("` .*")
                reasoning = " ".join(lines[:-1])[:200] if len(lines) > 1 else ""

                self._think(f"LLM reasoning: {reasoning}")
                self._think(f"LLM chose: {chosen}")

                if chosen == "rest" or not chosen:
                    return None

                for name in self.actions:
                    if name.lower() == chosen:
                        return name

                for name in self.actions:
                    if name.lower() in chosen or chosen in name.lower():
                        return name

                return None

        except httpx.HTTPError as exc:
            logger.warning("Ollama request failed: %s", exc)
            self._think(f"Ollama failed: {exc}")
            return None

    def _build_perception_summary(self, p: Perception) -> str:
        """Build a rich text summary of perception for the LLM."""
        last_result = ""
        if self.state.last_action_result:
            last_result = f" => {self.state.last_action_result[:120]}"
        parts = [
            f"Cycle: {self.state.cycle_count}",
            f"Last action: {self.state.last_action or 'none'}{last_result}",
            f"Skill gaps: {len(p.skill_gaps)} domains below floor",
            f"Total failed problems: {len(p.failed_problems)}",
            f"Total completed problems: {len(p.completed_problems)}",
            f"Available models: {', '.join(p.available_models[:5]) or 'none'}",
            f"Circuit breaker: {p.circuit_breaker_state}",
        ]

        if p.resource_usage:
            parts.append(
                f"Resources: CPU {p.resource_usage.get('cpu_pct', 0):.0f}%, "
                f"Mem {p.resource_usage.get('memory_pct', 0):.0f}%"
            )

        if p.skill_gaps:
            gap_details = []
            for g in p.skill_gaps[:5]:
                gap_details.append(
                    f"  {g['domain_name']}: {g['permanent_count']}/{g['floor']} skills "
                    f"(gap={g['gap_score']:.0%})"
                )
            parts.append("Skill gap details:\n" + "\n".join(gap_details))

        if self.state.recent_failures:
            fail_details = []
            for f in self.state.recent_failures[-3:]:
                fail_details.append(
                    f"  cycle {f.get('cycle')}: {f.get('action')} — {f.get('summary', '')[:100]}"
                )
            parts.append(f"Recent failures ({len(self.state.recent_failures)} total):\n" + "\n".join(fail_details))

        if self.state.recent_successes:
            succ_details = []
            for s in self.state.recent_successes[-3:]:
                succ_details.append(
                    f"  cycle {s.get('cycle')}: {s.get('action')} — {s.get('summary', '')[:80]}"
                )
            parts.append(f"Recent successes ({len(self.state.recent_successes)} total):\n" + "\n".join(succ_details))

        action_counts = Counter(
            e.get("action", "") for e in
            (self.state.recent_successes[-10:] + self.state.recent_failures[-10:])
        )
        if action_counts:
            dist = ", ".join(f"{k}={v}" for k, v in action_counts.most_common(5))
            parts.append(f"Action distribution (last 10): {dist}")

        model_names = [m for m in p.available_models if "embed" not in m]
        if len(model_names) < 3:
            parts.append(
                f"NOTE: Only {len(model_names)} non-embedding model(s) available. "
                f"Consider pull_model to expand capabilities."
            )
        elif not any("benchmark" in e.get("action", "") for e in self.state.recent_successes[-20:]):
            parts.append(
                f"NOTE: {len(model_names)} models available but never benchmarked. "
                f"Consider benchmark_models to compare quality/speed."
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
        """Log a thought with timestamp and buffer for Redis sync."""
        ts = datetime.now(UTC).isoformat()
        line = f"[{ts}] {thought}\n"
        self._recent_thoughts.append(f"[{ts}] {thought}")
        self._recent_thoughts = self._recent_thoughts[-50:]
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
