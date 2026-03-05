"""Domain problem actions — run domain problems through the pipeline."""
from __future__ import annotations

__pattern__ = "Strategy"

import json
import logging
import uuid as uuid_mod
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
            return 0.7
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

            skills_ingested = pr.skills_ingested

            if pr.status == "complete":
                created = await self._create_skill_from_completion(
                    gap.domain_id,
                    gap.domain_name,
                    gap.scenario.get("title", ""),
                    gap.skill_category,
                    pr.problem_uuid,
                )
                if created:
                    skills_ingested += 1

            artifacts = {
                "problem_uuid": pr.problem_uuid,
                "domain_id": pr.domain_id,
                "scenario_id": pr.scenario_id,
                "status": pr.status,
                "judge_verdict": pr.judge_verdict,
                "judge_score": pr.judge_score,
                "skills_ingested": skills_ingested,
                "error": pr.error,
            }
            success = pr.status == "complete"
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

    async def _create_skill_from_completion(
        self,
        domain_id: str,
        domain_name: str,
        scenario_title: str,
        skill_category: str,
        problem_uuid: str,
    ) -> bool:
        """Create a probationary skill from a completed problem."""
        try:
            skill_name = f"{domain_name} — {scenario_title}"
            description = (
                f"Skill acquired from solving {scenario_title} "
                f"in the {domain_name} domain (problem {problem_uuid[:8]})"
            )
            db_category = skill_category if skill_category else "analysis"
            keywords = [domain_id, skill_category, scenario_title.lower().replace(" ", "_")]

            async with httpx.AsyncClient(base_url=self.api_url, timeout=15) as client:
                resp = await client.post(
                    "/api/skills",
                    json={
                        "name": skill_name,
                        "description": description,
                        "category": db_category,
                        "trigger_keywords": keywords,
                        "problem_id": problem_uuid,
                    },
                )
                if resp.status_code in (200, 201):
                    logger.info("Created probationary skill: %s", skill_name)
                    return True
                logger.warning(
                    "Skill creation returned %d: %s",
                    resp.status_code, resp.text[:200],
                )
                return False
        except Exception as exc:
            logger.warning("Could not create skill: %s", exc)
            return False
