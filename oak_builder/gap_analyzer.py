"""Gap analyzer — reads manifest_domains.json and queries the OAK API
to identify which business domains have the fewest permanent skills.

Rotates through scenario templates across sprints to ensure breadth.
"""
from __future__ import annotations

__pattern__ = "Strategy"

import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger("oak.builder.gap_analyzer")

MANIFEST_DOMAINS_PATH = Path("/oak-repo/manifest_domains.json")


@dataclass
class Gap:
    domain_id: str
    domain_name: str
    skill_category: str
    permanent_count: int
    floor: int
    gap_score: float
    scenario: dict


async def analyze_gaps(
    api_url: str,
    *,
    sprint_number: int = 0,
    top_n: int = 3,
    manifest_path: Path | None = None,
) -> list[Gap]:
    """Return the top-N domain gaps, each with a selected scenario template.

    Scenario selection rotates based on ``sprint_number`` so that successive
    sprints explore different problem types within the same domain.
    """
    path = manifest_path or MANIFEST_DOMAINS_PATH
    if not path.exists():
        logger.error("manifest_domains.json not found at %s", path)
        return []

    manifest = json.loads(path.read_text())
    domains = manifest["domains"]
    floor = manifest.get("floor_permanent_skills_per_domain", 3)

    gaps: list[Gap] = []
    async with httpx.AsyncClient(base_url=api_url, timeout=15) as client:
        telemetry = {}
        try:
            resp = await client.get("/api/telemetry")
            if resp.status_code == 200:
                telemetry = resp.json()
        except httpx.HTTPError:
            logger.warning("Could not fetch telemetry, continuing without it")

        for domain in domains:
            domain_id = domain["id"]
            category = domain.get("skill_category", domain_id)
            permanent_count = 0

            try:
                resp = await client.get(
                    "/api/skills",
                    params={"status": "permanent", "category": category, "top_k": 50},
                )
                if resp.status_code == 200:
                    skills = resp.json()
                    permanent_count = len(skills) if isinstance(skills, list) else 0
            except httpx.HTTPError:
                logger.warning("Could not query skills for domain %s", domain_id)

            if permanent_count >= floor:
                gap_score = 0.0
            else:
                gap_score = (floor - permanent_count) / floor

            telemetry_penalty = _telemetry_penalty(telemetry, domain_id)
            gap_score = min(gap_score + telemetry_penalty, 1.0)

            scenarios = domain.get("scenarios", [])
            if not scenarios:
                continue
            selected = scenarios[sprint_number % len(scenarios)]

            gaps.append(Gap(
                domain_id=domain_id,
                domain_name=domain["name"],
                skill_category=category,
                permanent_count=permanent_count,
                floor=floor,
                gap_score=gap_score,
                scenario=selected,
            ))

    random.shuffle(gaps)
    gaps.sort(key=lambda g: g.gap_score, reverse=True)
    selected = gaps[:top_n]

    for g in selected:
        logger.info(
            "Gap: %s (score=%.2f, skills=%d/%d, scenario=%s)",
            g.domain_name, g.gap_score, g.permanent_count, g.floor,
            g.scenario.get("id", "?"),
        )

    return selected


def _telemetry_penalty(telemetry: dict, domain_id: str) -> float:
    """Add a small penalty for domains with poor telemetry signals."""
    events_by_type = telemetry.get("events_by_type", {})
    failure_count = events_by_type.get(f"task_failed_{domain_id}", 0)
    if failure_count > 3:
        return 0.2
    if failure_count > 0:
        return 0.1
    return 0.0
