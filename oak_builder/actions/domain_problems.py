"""Domain problem actions — run domain problems through the pipeline."""
from __future__ import annotations

__pattern__ = "Strategy"

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from oak_builder.cortex import Action, ActionResult, CortexState, Perception
from oak_builder.gap_analyzer import analyze_gaps
from oak_builder.pipeline_runner import run_problem
from oak_builder.problem_generator import generate_problem

if TYPE_CHECKING:
    from oak_builder.cortex import CortexState, Perception

logger = logging.getLogger("oak.builder.actions.domain_problems")

MANIFEST_DOMAINS_PATH = Path("/oak-repo/manifest_domains.json")
WORKSPACE_BASE = "/workspaces"


class RunDomainProblem(Action):
    """Run a domain problem: analyze gaps, generate dataset, submit, run pipeline, ingest skills."""

    name = "run_domain_problem"
    category = "domain"

    async def estimate_value(
        self, state: CortexState, perception: Perception
    ) -> float:
        skill_gaps = len(getattr(perception, "skill_gaps", [])) > 0
        if skill_gaps:
            return 0.95
        return 0.2

    async def execute(self, state: CortexState) -> ActionResult:
        manifest_path = MANIFEST_DOMAINS_PATH
        workspace_base = WORKSPACE_BASE
        sprint_number = getattr(state, "cycle_count", 0)
        top_n = 1

        try:
            if not manifest_path.exists():
                return ActionResult(
                    success=False,
                    summary=f"manifest_domains.json not found at {manifest_path}",
                )
            manifest = json.loads(manifest_path.read_text())
            manifest_companies = manifest.get("canonical_companies", {})

            gaps = await analyze_gaps(
                self.api_url,
                sprint_number=sprint_number,
                top_n=top_n,
                manifest_path=manifest_path,
            )
            if not gaps:
                return ActionResult(
                    success=True,
                    summary="No gaps to address",
                    artifacts={"message": "No gaps to address"},
                )

            gap = gaps[0]
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
                    summary="Could not generate problem",
                )

            pr = await run_problem(
                problem,
                api_url=self.api_url,
                pause_check=None,
            )

            artifacts = {
                "problem_uuid": pr.problem_uuid,
                "domain_id": pr.domain_id,
                "scenario_id": pr.scenario_id,
                "status": pr.status,
                "judge_verdict": pr.judge_verdict,
                "judge_score": pr.judge_score,
                "skills_ingested": pr.skills_ingested,
                "error": pr.error,
            }
            success = pr.status == "complete" and pr.judge_verdict == "pass"
            summary = f"{pr.domain_id}: {pr.status}" + (
                f" ({pr.judge_verdict})" if pr.judge_verdict else ""
            )
            if pr.error:
                summary = pr.error
            return ActionResult(
                success=success,
                summary=summary,
                artifacts=artifacts,
            )
        except Exception as exc:
            logger.exception("RunDomainProblem failed")
            return ActionResult(success=False, summary=str(exc))
