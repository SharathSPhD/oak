"""Manifest actions: propose and ratify amendments."""
from __future__ import annotations

__pattern__ = "Strategy"

import logging
from pathlib import Path

import httpx

from oak_builder.cortex import Action, ActionResult, CortexState, Perception

logger = logging.getLogger("oak.builder.actions.manifest")


class ProposeAmendment(Action):
    """Analyze demonstrated capabilities vs manifest, draft amendment. Requires 3 evidence runs."""

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
        return "propose_amendment"

    @property
    def category(self) -> str:
        return "manifest"

    async def estimate_value(self, state: CortexState, perception: Perception) -> float:
        evidence = state.get("amendment_evidence_runs", [])
        if len(evidence) >= 2 and state.get("demonstrated_capabilities"):
            return 0.85
        if evidence:
            return 0.5
        return 0.2

    async def execute(self, state: CortexState) -> ActionResult:
        evidence = state.get("amendment_evidence_runs", [])
        if len(evidence) < 3:
            return ActionResult(
                success=False,
                summary=f"Need 3 evidence runs before proposing amendment (have {len(evidence)})",
            )

        manifest_path = Path(self.repo_path) / "manifestv1.0.md"
        if not manifest_path.exists():
            manifest_path = Path(self.repo_path) / "spec.md"
        if not manifest_path.exists():
            return ActionResult(success=False, summary="Manifest not found")

        capabilities = state.get("demonstrated_capabilities", {})
        manifest_content = manifest_path.read_text()

        try:
            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.post(
                    f"{self.ollama_url}/v1/chat/completions",
                    headers={"Authorization": "Bearer ollama"},
                    json={
                        "model": "qwen3-coder",
                        "messages": [
                            {
                                "role": "user",
                                "content": (
                                    "Analyze demonstrated capabilities vs manifest. "
                                    f"Evidence: {evidence}. Capabilities: {capabilities}. "
                                    "Draft a manifest amendment (markdown) that adds or updates "
                                    "sections to reflect demonstrated capabilities. "
                                    "Return only the amendment text."
                                ),
                            },
                            {"role": "user", "content": manifest_content[:6000]},
                        ],
                        "stream": False,
                    },
                )
                if resp.status_code != 200:
                    return ActionResult(success=False, summary=f"Ollama failed: {resp.status_code}")
                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    return ActionResult(success=False, summary="No response from Ollama")
                amendment = choices[0].get("message", {}).get("content", "").strip()

            amendment_path = Path(self.workspace_base) / "builder" / "manifest_amendment.md"
            amendment_path.parent.mkdir(parents=True, exist_ok=True)
            amendment_path.write_text(amendment)

            state.setdefault("pending_amendment", {})
            state["pending_amendment"] = {
                "path": str(amendment_path),
                "evidence_count": len(evidence),
            }

            logger.info("Proposed amendment with %d evidence runs", len(evidence))
            return ActionResult(
                success=True,
                artifacts={
                    "amendment_path": str(amendment_path),
                    "evidence_count": len(evidence),
                },
            )
        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))


class RatifyAmendment(Action):
    """If 3+ evidence runs passed, merge amendment into manifest."""

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
        return "ratify_amendment"

    @property
    def category(self) -> str:
        return "manifest"

    async def estimate_value(self, state: CortexState, perception: Perception) -> float:
        pending = state.get("pending_amendment", {})
        evidence = state.get("amendment_evidence_runs", [])
        if pending and len(evidence) >= 3:
            return 0.9
        return 0.3

    async def execute(self, state: CortexState) -> ActionResult:
        pending = state.get("pending_amendment", {})
        evidence = state.get("amendment_evidence_runs", [])
        if len(evidence) < 3:
            return ActionResult(
                success=False,
                summary=f"Need 3+ evidence runs to ratify (have {len(evidence)})",
            )

        amendment_path = pending.get("path") or str(
            Path(self.workspace_base) / "builder" / "manifest_amendment.md"
        )
        if not Path(amendment_path).exists():
            return ActionResult(success=False, summary=f"Amendment file not found: {amendment_path}")

        manifest_path = Path(self.repo_path) / "manifestv1.0.md"
        if not manifest_path.exists():
            manifest_path = Path(self.repo_path) / "spec.md"
        if not manifest_path.exists():
            return ActionResult(success=False, summary="Manifest not found")

        try:
            amendment = Path(amendment_path).read_text()
            manifest_content = manifest_path.read_text()
            merged = (
                manifest_content.rstrip()
                + "\n\n---\n\n## Amendment (ratified)\n\n"
                + amendment
            )
            manifest_path.write_text(merged)

            Path(amendment_path).unlink(missing_ok=True)
            if "pending_amendment" in state:
                del state["pending_amendment"]

            logger.info("Ratified amendment, merged into %s", manifest_path)
            return ActionResult(
                success=True,
                artifacts={"manifest": str(manifest_path), "evidence_count": len(evidence)},
            )
        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))
