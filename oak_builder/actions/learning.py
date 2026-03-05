"""Learning actions — web research, HuggingFace harvest, paper reading."""
from __future__ import annotations

__pattern__ = "Strategy"

import logging
import re
from html.parser import HTMLParser
from typing import TYPE_CHECKING
from urllib.parse import quote_plus

import httpx

from oak_builder.cortex import Action, ActionResult, CortexState, Perception

if TYPE_CHECKING:
    from oak_builder.cortex import CortexState, Perception

logger = logging.getLogger("oak.builder.actions.learning")


class _DuckDuckGoResultParser(HTMLParser):
    """Parse DuckDuckGo HTML results for links and snippets."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._in_result = False
        self._current_link: str | None = None
        self._current_snippet: str = ""
        self._in_snippet = False
        self._in_link = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_d = dict((k, v or "") for k, v in attrs)
        if tag == "a" and "result__a" in attrs_d.get("class", ""):
            self._in_link = True
            href = attrs_d.get("href", "")
            if href.startswith("http") and "duckduckgo.com" not in href:
                self._current_link = href
        elif tag == "a" and self._in_result and "result__snippet" in attrs_d.get("class", ""):
            self._in_snippet = True
        if tag == "div" and "result__body" in attrs_d.get("class", ""):
            self._in_result = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._in_result:
            if self._current_link and self._current_snippet:
                self.results.append({
                    "url": self._current_link,
                    "snippet": self._current_snippet[:500].strip(),
                })
            self._in_result = False
            self._current_link = None
            self._current_snippet = ""
        if tag == "a":
            self._in_link = False
            self._in_snippet = False

    def handle_data(self, data: str) -> None:
        if self._in_snippet or (self._in_link and self._in_result):
            self._current_snippet = (self._current_snippet + " " + data).strip()


def _parse_ddg_html(html: str) -> list[dict[str, str]]:
    """Extract top result links and snippets from DuckDuckGo HTML."""
    parser = _DuckDuckGoResultParser()
    try:
        parser.feed(html)
        return parser.results[:5]
    except Exception:
        pass
    results: list[dict[str, str]] = []
    link_pattern = re.compile(r'href="(https?://[^"]+)"[^>]*class="[^"]*result__a')
    for m in link_pattern.finditer(html):
        url = m.group(1)
        if "duckduckgo.com" in url:
            continue
        results.append({"url": url, "snippet": ""})
        if len(results) >= 5:
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
        pending = getattr(state, "pending_research", [])
        if not pending:
            query = "OAK autonomous builder analytics"
        else:
            first = pending[0]
            query = str(first) if isinstance(first, str) else str(first.get("query", ""))

        try:
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    url,
                    headers={"User-Agent": "OAK-Builder/1.0"},
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
