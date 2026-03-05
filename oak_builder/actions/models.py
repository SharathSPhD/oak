"""Model management actions: pull, benchmark, update routing."""
from __future__ import annotations

__pattern__ = "Strategy"

import asyncio
import logging
from typing import Any

import httpx

from oak_builder.cortex import Action, ActionResult, CortexState, Perception

logger = logging.getLogger("oak.builder.actions.models")

OLLAMA_DIRECT = "http://oak-ollama:11434"


class PullModel(Action):
    """Pull an Ollama model and verify with benchmark."""

    def __init__(
        self,
        api_url: str,
        ollama_url: str,
        repo_path: str = "/oak-repo",
        workspace_base: str = "/workspaces",
    ) -> None:
        super().__init__(api_url=api_url, ollama_url=ollama_url)
        self.repo_path = repo_path
        self.workspace_base = workspace_base

    @property
    def name(self) -> str:
        return "pull_model"

    @property
    def category(self) -> str:
        return "models"

    async def estimate_value(self, state: CortexState, perception: Perception) -> float:
        harvest = state.get("harvest_hf", {})
        if harvest.get("promising_model"):
            return 0.9
        models = state.get("available_models", [])
        if len(models) <= 1 and models:
            return 0.7
        if harvest or models:
            return 0.5
        return 0.2

    async def execute(self, state: CortexState) -> ActionResult:
        model_name = (
            state.get("harvest_hf", {}).get("promising_model")
            or state.get("model_to_pull")
            or (state.get("available_models", [None])[0] if state.get("available_models") else None)
        )
        if not model_name:
            return ActionResult(success=False, summary="No model name to pull")

        try:
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(
                    f"{OLLAMA_DIRECT}/api/pull",
                    json={"name": model_name, "stream": False},
                )
                if resp.status_code != 200:
                    return ActionResult(
                        success=False,
                        summary=f"Pull failed: {resp.status_code} {resp.text[:200]}",
                    )

                tags_resp = await client.get(f"{OLLAMA_DIRECT}/api/tags")
                if tags_resp.status_code != 200:
                    return ActionResult(success=False, summary="Could not verify tags after pull")

                tags_data = tags_resp.json()
                models = [m.get("name") for m in tags_data.get("models", [])]
                if model_name not in models:
                    return ActionResult(
                        success=False,
                        summary=f"Model {model_name} not found in tags after pull",
                    )

                logger.info("Pulled model %s, running benchmark", model_name)
                benchmark_result = await _run_small_benchmark(client, model_name)
                return ActionResult(
                    success=True,
                    artifacts={
                        "model": model_name,
                        "benchmark": benchmark_result,
                    },
                )
        except httpx.HTTPError as exc:
            return ActionResult(success=False, summary=str(exc))


async def _run_small_benchmark(client: httpx.AsyncClient, model_name: str) -> dict[str, Any]:
    """Run a minimal test problem to benchmark the model."""
    try:
        resp = await client.post(
            f"{OLLAMA_DIRECT}/api/generate",
            json={
                "model": model_name,
                "prompt": "Say 'ok' in one word.",
                "stream": False,
            },
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {"duration_ms": data.get("eval_duration", 0), "passed": True}
    except Exception as e:
        logger.warning("Benchmark failed: %s", e)
    return {"passed": False}


class BenchmarkModels(Action):
    """Benchmark two models on the same canonical problem and compare judge scores."""

    def __init__(
        self,
        api_url: str,
        ollama_url: str,
        repo_path: str = "/oak-repo",
        workspace_base: str = "/workspaces",
    ) -> None:
        super().__init__(api_url=api_url, ollama_url=ollama_url)
        self.repo_path = repo_path
        self.workspace_base = workspace_base

    @property
    def name(self) -> str:
        return "benchmark_models"

    @property
    def category(self) -> str:
        return "models"

    async def estimate_value(self, state: CortexState, perception: Perception) -> float:
        models = state.get("available_models", [])
        if len(models) >= 2:
            return 0.7
        if len(models) == 1:
            return 0.3
        return 0.1

    async def execute(self, state: CortexState) -> ActionResult:
        models = state.get("available_models", [])
        if len(models) < 2:
            return ActionResult(success=False, summary="Need at least 2 models to benchmark")

        model_a, model_b = models[0], models[1]
        try:
            async with httpx.AsyncClient(base_url=self.api_url, timeout=120) as client:
                score_a = await _run_canonical_problem(client, model_a)
                score_b = await _run_canonical_problem(client, model_b)

            benchmarks = {
                model_a: score_a,
                model_b: score_b,
            }
            state.setdefault("model_benchmarks", {})
            state["model_benchmarks"].update(benchmarks)

            return ActionResult(
                success=True,
                artifacts={
                    "benchmarks": benchmarks,
                    "winner": model_a if score_a >= score_b else model_b,
                },
            )
        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))


async def _run_canonical_problem(client: httpx.AsyncClient, model: str) -> float:
    """Submit a canonical problem and return judge score. Placeholder: uses API if available."""
    try:
        resp = await client.post(
            "/api/problems",
            json={
                "title": "Benchmark canonical",
                "description": "Minimal ETL benchmark",
                "model_override": model,
            },
            timeout=60,
        )
        if resp.status_code != 200:
            return 0.0
        data = resp.json()
        problem_id = data.get("id")
        if not problem_id:
            return 0.0
        await asyncio.sleep(30)
        verdict_resp = await client.get(f"/api/problems/{problem_id}/verdict")
        if verdict_resp.status_code != 200:
            return 0.0
        v = verdict_resp.json()
        return 1.0 if v.get("verdict") == "pass" else 0.0
    except Exception:
        return 0.0


class UpdateRouting(Action):
    """Update model_for_role mapping when benchmarks show a better model for a role."""

    def __init__(
        self,
        api_url: str,
        ollama_url: str,
        repo_path: str = "/oak-repo",
        workspace_base: str = "/workspaces",
    ) -> None:
        super().__init__(api_url=api_url, ollama_url=ollama_url)
        self.repo_path = repo_path
        self.workspace_base = workspace_base

    @property
    def name(self) -> str:
        return "update_routing"

    @property
    def category(self) -> str:
        return "models"

    async def estimate_value(self, state: CortexState, perception: Perception) -> float:
        benchmarks = state.get("model_benchmarks", {})
        model_for_role = state.get("model_for_role", {})
        if benchmarks and model_for_role:
            for _role, current in model_for_role.items():
                for model, score in benchmarks.items():
                    if model != current and score > 0.7:
                        return 0.85
        return 0.3

    async def execute(self, state: CortexState) -> ActionResult:
        benchmarks = state.get("model_benchmarks", {})
        model_for_role = state.get("model_for_role", {})
        if not benchmarks:
            return ActionResult(success=False, summary="No benchmark data available")

        changes: list[dict[str, str]] = []
        for role, current_model in model_for_role.items():
            best_model = max(benchmarks, key=lambda m: benchmarks.get(m, 0))
            best_score = benchmarks.get(best_model, 0)
            if best_model != current_model and best_score >= 0.7:
                changes.append({"role": role, "from": current_model, "to": best_model})

        if not changes:
            return ActionResult(
                success=True,
                artifacts={"message": "No routing updates needed"},
            )

        try:
            async with httpx.AsyncClient(base_url=self.api_url, timeout=30) as client:
                resp = await client.patch(
                    "/api/config/model-routing",
                    json={"model_for_role": {c["role"]: c["to"] for c in changes}},
                )
                if resp.status_code in (200, 204):
                    for c in changes:
                        logger.info(
                            "Updated routing: %s %s -> %s",
                            c["role"], c["from"], c["to"],
                        )
                    return ActionResult(
                        success=True,
                        artifacts={"changes": changes},
                    )
                return ActionResult(
                    success=False,
                    summary=f"Config update failed: {resp.status_code}",
                )
        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))
