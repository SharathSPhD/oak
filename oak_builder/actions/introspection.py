"""Introspection actions — audit, replay failures, benchmark regression."""
from __future__ import annotations

__pattern__ = "Strategy"

import json
import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from oak_builder.cortex import Action, ActionResult, CortexState, Perception

if TYPE_CHECKING:
    from oak_builder.cortex import CortexState, Perception

logger = logging.getLogger("oak.builder.actions.introspection")

MANIFEST_DOMAINS_PATH = Path("/oak-repo/manifest_domains.json")
WORKSPACE_BASE = "/workspaces"
SPRINT_LOG_PATH = "/workspaces/builder/sprint_log.json"


class AuditSelf(Action):
    """Audit builder state against manifest_domains.json and produce gap report."""

    name = "audit_self"
    category = "introspection"

    async def estimate_value(
        self, state: CortexState, perception: Perception
    ) -> float:
        cycle_count = getattr(state, "cycle_count", 0)
        if cycle_count % 20 == 0:
            return 0.7
        return 0.25

    async def execute(self, state: CortexState) -> ActionResult:
        manifest_path = MANIFEST_DOMAINS_PATH
        try:
            async with httpx.AsyncClient(
                base_url=self.api_url, timeout=30
            ) as client:
                telemetry = {}
                skills = []
                problems = []
                try:
                    resp = await client.get("/api/telemetry")
                    if resp.status_code == 200:
                        telemetry = resp.json()
                except httpx.HTTPError as exc:
                    logger.warning("Could not fetch telemetry: %s", exc)
                try:
                    resp = await client.get("/api/problems")
                    if resp.status_code == 200:
                        data = resp.json()
                        problems = data if isinstance(data, list) else []
                except httpx.HTTPError as exc:
                    logger.warning("Could not fetch problems: %s", exc)

            if not manifest_path.exists():
                return ActionResult(
                    success=False,
                    summary=f"manifest_domains.json not found at {manifest_path}",
                )

            manifest = json.loads(manifest_path.read_text())
            domains = manifest.get("domains", [])
            floor = manifest.get("floor_permanent_skills_per_domain", 3)
            target = manifest.get("target_permanent_skills_per_domain", 10)

            gap_report: list[dict] = []
            async with httpx.AsyncClient(
                base_url=self.api_url, timeout=15
            ) as skill_client:
                for domain in domains:
                    domain_id = domain.get("id", "?")
                    category = domain.get("skill_category", domain_id)
                    permanent_count = 0
                    try:
                        s_resp = await skill_client.get(
                            "/api/skills",
                            params={
                                "status": "permanent",
                                "category": category,
                                "top_k": 50,
                            },
                        )
                        if s_resp.status_code == 200:
                            skills_list = s_resp.json()
                            permanent_count = len(skills_list) if isinstance(skills_list, list) else 0
                    except httpx.HTTPError:
                        pass
                    gap = floor - permanent_count if permanent_count < floor else 0
                    gap_report.append({
                        "domain_id": domain_id,
                        "domain_name": domain.get("name", domain_id),
                        "permanent_skills": permanent_count,
                        "floor": floor,
                        "target": target,
                        "gap": gap,
                        "status": "ok" if gap == 0 else "below_floor",
                    })

            active_count = sum(
                1 for p in problems
                if p.get("status") in ("active", "assembling")
            )

            artifacts = {
                "gap_report": gap_report,
                "telemetry_summary": {
                    "total_events": telemetry.get("total_events", 0),
                    "escalation_rate_pct": telemetry.get("escalation_rate_pct", 0),
                    "active_problems": telemetry.get("active_problems", active_count),
                },
                "domains_audited": len(domains),
            }
            return ActionResult(
                success=True,
                summary=f"Audited {len(domains)} domains",
                artifacts=artifacts,
            )
        except Exception as exc:
            logger.exception("AuditSelf failed")
            return ActionResult(success=False, summary=str(exc))


class ReplayFailure(Action):
    """Analyze most recent failed problem and categorize failure type."""

    name = "replay_failure"
    category = "introspection"

    async def estimate_value(
        self, state: CortexState, perception: Perception
    ) -> float:
        recent_failures = getattr(state, "recent_failures", [])
        if not recent_failures:
            return 0.1
        recent_replays = sum(
            1 for s in getattr(state, "recent_successes", [])[-10:]
            if s.get("action") == "replay_failure"
        )
        if recent_replays >= 2:
            return 0.15
        return 0.5

    async def execute(self, state: CortexState) -> ActionResult:
        try:
            async with httpx.AsyncClient(
                base_url=self.api_url, timeout=30
            ) as client:
                resp = await client.get("/api/problems")
                if resp.status_code != 200:
                    return ActionResult(
                        success=False,
                        summary="Could not fetch problems",
                    )
                problems = resp.json()
                if not isinstance(problems, list):
                    return ActionResult(success=False, summary="Invalid problems response")

                failed = [
                    p for p in problems
                    if p.get("status") == "failed"
                ]
                if not failed:
                    return ActionResult(
                        success=True,
                        summary="No failed problems to replay",
                        artifacts={"message": "No failed problems to replay"},
                    )

                most_recent = failed[-1]
                problem_uuid = most_recent.get("id", most_recent.get("uuid", ""))
                if not problem_uuid:
                    return ActionResult(success=False, summary="No problem UUID")

                tasks: list[dict] = []
                try:
                    task_resp = await client.get(
                        "/api/tasks",
                        params={"problem_id": problem_uuid},
                    )
                    if task_resp.status_code == 200:
                        data = task_resp.json()
                        tasks = data if isinstance(data, list) else []
                except httpx.HTTPError:
                    pass

                failed_tasks = [t for t in tasks if t.get("status") == "failed"]
                diagnosis = "unknown"
                if failed_tasks:
                    last_failed = failed_tasks[-1]
                    error_msg = (last_failed.get("error") or last_failed.get("output") or "").lower()
                    if "syntax" in error_msg or "import" in error_msg or "traceback" in error_msg:
                        diagnosis = "code_failure"
                    elif "csv" in error_msg or "data" in error_msg or "column" in error_msg:
                        diagnosis = "data_failure"
                    elif "model" in error_msg or "ollama" in error_msg or "timeout" in error_msg:
                        diagnosis = "model_failure"
                    elif "decompos" in error_msg or "task" in error_msg:
                        diagnosis = "decomposition_failure"
                    else:
                        diagnosis = "code_failure"

                logs_snippet = ""
                try:
                    logs_resp = await client.get(
                        f"/api/problems/{problem_uuid}/logs"
                    )
                    if logs_resp.status_code == 200:
                        data = logs_resp.json()
                        if isinstance(data, dict) and "logs" in data:
                            logs_snippet = (data["logs"] or "")[-2000:]
                except httpx.HTTPError:
                    pass

                if not logs_snippet and problem_uuid:
                    try:
                        result = subprocess.run(
                            ["docker", "logs", "--tail", "100",
                             f"oak-harness-{problem_uuid}"],
                            capture_output=True, text=True, timeout=10,
                        )
                        logs_snippet = (result.stdout or result.stderr or "")[-2000:]
                    except Exception:
                        pass

                if "syntax" in logs_snippet or "ImportError" in logs_snippet:
                    diagnosis = "code_failure"
                elif "model" in logs_snippet or "ollama" in logs_snippet:
                    diagnosis = "model_failure"

                artifacts = {
                    "problem_uuid": problem_uuid,
                    "diagnosis": diagnosis,
                    "failed_tasks_count": len(failed_tasks),
                    "total_tasks": len(tasks),
                }
                return ActionResult(
                    success=True,
                    summary=f"Diagnosis: {diagnosis}",
                    artifacts=artifacts,
                )
        except Exception as exc:
            logger.exception("ReplayFailure failed")
            return ActionResult(success=False, summary=str(exc))


class BenchmarkRegression(Action):
    """Run canonical problem and compare judge score against baseline."""

    name = "benchmark_regression"
    category = "introspection"

    async def estimate_value(
        self, state: CortexState, perception: Perception
    ) -> float:
        cycle_count = getattr(state, "cycle_count", 0)
        if cycle_count > 0 and cycle_count % 50 == 0:
            return 0.6
        return 0.2

    async def execute(self, state: CortexState) -> ActionResult:
        manifest_path = MANIFEST_DOMAINS_PATH
        sprint_log_path = SPRINT_LOG_PATH
        try:
            if not manifest_path.exists():
                return ActionResult(
                    success=False,
                    summary=f"manifest_domains.json not found at {manifest_path}",
                )
            manifest = json.loads(manifest_path.read_text())
            domains = manifest.get("domains", [])
            if not domains:
                return ActionResult(success=False, summary="No domains in manifest")

            domain = domains[0]
            scenario = domain.get("scenarios", [{}])[0]
            baseline = None
            if Path(sprint_log_path).exists():
                try:
                    log_data = json.loads(Path(sprint_log_path).read_text())
                    baseline = log_data.get("domain_baselines", {}).get(
                        domain.get("id", ""),
                    )
                except Exception:
                    pass

            from oak_builder.gap_analyzer import Gap, analyze_gaps
            from oak_builder.pipeline_runner import run_problem
            from oak_builder.problem_generator import generate_problem

            gaps = await analyze_gaps(
                self.api_url,
                sprint_number=getattr(state, "cycle_count", 0),
                top_n=1,
                manifest_path=manifest_path,
            )
            if not gaps:
                return ActionResult(
                    success=True,
                    summary="No gaps to benchmark",
                    artifacts={"message": "No gaps to benchmark"},
                )

            gap = gaps[0]
            workspace_base = WORKSPACE_BASE
            manifest_companies = manifest.get("canonical_companies", {})

            problem = await generate_problem(
                gap,
                workspace_base=workspace_base,
                ollama_url=self.ollama_url,
                model="qwen3-coder",
                manifest_companies=manifest_companies,
            )
            if not problem:
                return ActionResult(
                    success=False,
                    summary="Could not generate benchmark problem",
                )

            pr = await run_problem(
                problem,
                api_url=self.api_url,
                pause_check=None,
            )

            current_score = pr.judge_score
            regressed = False
            if baseline is not None and current_score is not None:
                regressed = current_score < baseline

            artifacts = {
                "domain_id": gap.domain_id,
                "scenario_id": gap.scenario_id,
                "baseline_score": baseline,
                "current_score": current_score,
                "regressed": regressed,
                "status": pr.status,
                "verdict": pr.judge_verdict,
            }
            if baseline is not None:
                summary = f"Score {current_score} vs baseline {baseline}"
                if regressed:
                    summary += " (regressed)"
            else:
                summary = f"Score {current_score} (no baseline)"
            return ActionResult(success=True, summary=summary, artifacts=artifacts)
        except Exception as exc:
            logger.exception("BenchmarkRegression failed")
            return ActionResult(success=False, summary=str(exc))
