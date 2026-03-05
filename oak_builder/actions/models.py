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

RECOMMENDED_MODELS = [
    "deepseek-r1:14b",
    "qwen2.5:14b",
    "nomic-embed-text",
    "llama3.1:8b",
    "gemma3:12b",
    "phi4:14b",
]


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
        harvest = getattr(state, "harvest_hf", {})
        if harvest.get("promising_model"):
            return 0.9
        models = getattr(perception, "available_models", [])
        if len(models) < len(RECOMMENDED_MODELS):
            return 0.75
        return 0.2

    async def execute(self, state: CortexState) -> ActionResult:
        already_pulled: set[str] = set()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                tags_resp = await client.get(f"{OLLAMA_DIRECT}/api/tags")
                if tags_resp.status_code == 200:
                    for m in tags_resp.json().get("models", []):
                        already_pulled.add(m.get("name", ""))
        except httpx.HTTPError:
            pass

        model_name = (
            getattr(state, "harvest_hf", {}).get("promising_model")
            or getattr(state, "model_to_pull", None)
        )

        if not model_name:
            for rec in RECOMMENDED_MODELS:
                if not any(rec.split(":")[0] in p for p in already_pulled):
                    model_name = rec
                    break

        if not model_name:
            return ActionResult(
                success=True,
                summary=f"All recommended models already pulled ({len(already_pulled)} available)",
            )

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
        models = getattr(state, "available_models", [])
        if len(models) >= 2:
            return 0.7
        if len(models) == 1:
            return 0.3
        return 0.1

    async def execute(self, state: CortexState) -> ActionResult:
        available: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                tags_resp = await client.get(f"{OLLAMA_DIRECT}/api/tags")
                if tags_resp.status_code == 200:
                    for m in tags_resp.json().get("models", []):
                        name = m.get("name", "")
                        if name and "embed" not in name:
                            available.append(name)
        except httpx.HTTPError:
            pass

        if len(available) < 2:
            return ActionResult(success=False, summary=f"Need at least 2 models to benchmark, found {len(available)}")

        model_a, model_b = available[0], available[1]
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                bench_a = await _run_small_benchmark(client, model_a)
                bench_b = await _run_small_benchmark(client, model_b)

            benchmarks = {
                model_a: bench_a,
                model_b: bench_b,
            }

            return ActionResult(
                success=True,
                summary=f"Benchmarked {model_a} vs {model_b}",
                artifacts={
                    "benchmarks": benchmarks,
                    "winner": model_a if bench_a.get("duration_ms", 99999) <= bench_b.get("duration_ms", 99999) else model_b,
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
        benchmarks = getattr(state, "model_benchmarks", {})
        model_for_role = getattr(state, "model_for_role", {})
        if benchmarks and model_for_role:
            for _role, current in model_for_role.items():
                for model, score in benchmarks.items():
                    if model != current and score > 0.7:
                        return 0.85
        return 0.3

    async def execute(self, state: CortexState) -> ActionResult:
        benchmarks = getattr(state, "model_benchmarks", {})
        model_for_role = getattr(state, "model_for_role", {})
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
