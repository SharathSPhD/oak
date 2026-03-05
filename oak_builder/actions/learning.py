"""Learning actions — web research, HuggingFace harvest, paper reading."""
from __future__ import annotations

__pattern__ = "Strategy"

import logging
import re
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

from oak_builder.cortex import Action, ActionResult, CortexState, Perception

if TYPE_CHECKING:
    from oak_builder.cortex import CortexState, Perception

logger = logging.getLogger("oak.builder.actions.learning")

_BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _extract_real_url(href: str) -> str | None:
    """Extract real URL from DuckDuckGo redirect links."""
    if "uddg=" in href:
        parsed = urlparse(href if href.startswith("http") else f"https:{href}")
        qs = parse_qs(parsed.query)
        uddg = qs.get("uddg", [None])[0]
        if uddg:
            return unquote(uddg)
    if href.startswith("http") and "duckduckgo.com" not in href:
        return href
    return None


def _parse_ddg_html(html: str) -> list[dict[str, str]]:
    """Extract top result links and snippets from DuckDuckGo HTML via regex."""
    results: list[dict[str, str]] = []
    link_re = re.compile(
        r'class="[^"]*result__a[^"]*"\s+href="([^"]+)"'
        r"|"
        r'href="([^"]+)"[^>]*class="[^"]*result__a[^"]*"',
        re.DOTALL,
    )
    snippet_re = re.compile(
        r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    links = []
    for m in link_re.finditer(html):
        raw = m.group(1) or m.group(2)
        real = _extract_real_url(raw)
        if real:
            links.append((real, m.start()))

    snippets_by_pos: list[tuple[str, int]] = []
    for m in snippet_re.finditer(html):
        text = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        snippets_by_pos.append((text, m.start()))

    for url, pos in links:
        snippet = ""
        for stxt, spos in snippets_by_pos:
            if spos > pos:
                snippet = stxt[:500]
                break
        results.append({"url": url, "snippet": snippet})
        if len(results) >= 8:
            break
    return results


class WebResearch(Action):
    """Perform web research via DuckDuckGo and store results as episodes."""

    name = "web_research"
    category = "learning"

    async def estimate_value(
        self, state: CortexState, perception: Perception
    ) -> float:
        pending_research = getattr(state, "pending_research", [])
        skill_gaps = len(getattr(perception, "skill_gaps", [])) > 0
        if pending_research or skill_gaps:
            return 0.6
        return 0.2

    async def execute(self, state: CortexState) -> ActionResult:
        import random

        pending = getattr(state, "pending_research", [])
        if not pending:
            _default_queries = [
                "best practices multi-agent AI systems 2025",
                "ollama model performance benchmarks 2025",
                "autonomous AI software factory architecture",
                "data science pipeline automation best practices",
                "pgvector RAG retrieval augmented generation optimization",
                "self-improving AI agent architecture patterns",
                "small language model code generation comparison",
                "pandas data analysis advanced techniques",
                "fastapi production best practices async",
                "docker container orchestration self-healing patterns",
            ]
            query = random.choice(_default_queries)
        else:
            first = pending[0]
            query = str(first) if isinstance(first, str) else str(first.get("query", ""))

        try:
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    url,
                    headers={"User-Agent": _BROWSER_UA},
                )
                if resp.status_code != 200:
                    return ActionResult(
                        success=False,
                        summary=f"DuckDuckGo returned {resp.status_code}",
                    )
                results = _parse_ddg_html(resp.text)

            stored = 0
            for r in results:
                try:
                    async with httpx.AsyncClient(
                        base_url=self.api_url, timeout=10
                    ) as client:
                        post_resp = await client.post(
                            "/api/telemetry",
                            json={
                                "problem_id": None,
                                "agent_id": "oak-builder",
                                "event_type": "web_research",
                                "tool_name": "duckduckgo",
                                "tool_input": {"query": query, "url": r.get("url", "")},
                                "tool_response": {"snippet": r.get("snippet", "")},
                                "duration_ms": 0,
                                "escalated": False,
                            },
                        )
                        if post_resp.status_code in (200, 201):
                            stored += 1
                except httpx.HTTPError:
                    pass

            artifacts = {
                "query": query,
                "results_count": len(results),
                "episodes_stored": stored,
                "top_urls": [r.get("url", "") for r in results[:5]],
            }
            return ActionResult(
                success=True,
                summary=f"Found {len(results)} results, stored {stored}",
                artifacts=artifacts,
            )
        except Exception as exc:
            logger.exception("WebResearch failed")
            return ActionResult(success=False, summary=str(exc))


class HarvestHuggingFace(Action):
    """Fetch top text-generation models from HuggingFace and suggest promising ones."""

    name = "harvest_hf"
    category = "learning"

    async def estimate_value(
        self, state: CortexState, perception: Perception
    ) -> float:
        cycle_count = getattr(state, "cycle_count", 0)
        if cycle_count > 0 and cycle_count % 100 == 0:
            return 0.5
        return 0.15

    async def execute(self, state: CortexState) -> ActionResult:
        try:
            url = (
                "https://huggingface.co/api/models"
                "?filter=text-generation&sort=downloads&limit=10"
            )
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return ActionResult(
                        success=False,
                        summary=f"HuggingFace API returned {resp.status_code}",
                    )
                models = resp.json()
                if not isinstance(models, list):
                    return ActionResult(success=False, summary="Invalid HF response")

            current_models = {"qwen3-coder", "llama3.3:70b"}
            suggestions: list[dict] = []
            for m in models[:10]:
                model_id = m.get("id", "")
                downloads = m.get("downloads", 0)
                if not model_id:
                    continue
                id_lower = model_id.lower()
                if id_lower not in current_models and downloads > 10000:
                    suggestions.append({
                        "model_id": model_id,
                        "downloads": downloads,
                    })

            artifacts = {
                "models_checked": len(models),
                "suggestions": suggestions[:3],
                "current_models": list(current_models),
            }
            summary = f"Checked {len(models)} models, {len(suggestions[:3])} suggestions"
            return ActionResult(success=True, summary=summary, artifacts=artifacts)
        except Exception as exc:
            logger.exception("HarvestHuggingFace failed")
            return ActionResult(success=False, summary=str(exc))


class ReadPaper(Action):
    """Placeholder for paper reading — not yet implemented."""

    name = "read_paper"
    category = "learning"

    async def estimate_value(
        self, state: CortexState, perception: Perception
    ) -> float:
        return 0.05

    async def execute(self, state: CortexState) -> ActionResult:
        logger.info("Paper reading not yet implemented")
        return ActionResult(
            success=True,
            summary="Paper reading not yet implemented",
            artifacts={"message": "Paper reading not yet implemented"},
        )
