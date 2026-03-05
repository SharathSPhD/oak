"""Code change actions: improve prompts, harness, fix bugs, add features."""
from __future__ import annotations

__pattern__ = "Strategy"

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import httpx

from oak_builder.cortex import Action, ActionResult, CortexState, Perception

logger = logging.getLogger("oak.builder.actions.code_changes")


class ImprovePrompt(Action):
    """Improve agent prompt based on failure patterns."""

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
        return "improve_prompt"

    @property
    def category(self) -> str:
        return "code"

    async def estimate_value(self, state: CortexState, perception: Perception) -> float:
        if state.recent_failures:
            return 0.5
        return 0.2

    async def execute(self, state: CortexState) -> ActionResult:
        failure_patterns = state.recent_failures[-5:]
        role = "data-engineer"

        prompt_path = Path(self.repo_path) / ".claude" / "agents" / f"{role}.md"
        if not prompt_path.exists():
            return ActionResult(success=False, summary=f"Agent prompt not found: {prompt_path}")

        try:
            original = prompt_path.read_text()
            failure_summary = json.dumps(failure_patterns, indent=2)[:2000]
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.ollama_url}/v1/chat/completions",
                    json={
                        "model": "qwen3-coder",
                        "messages": [
                            {
                                "role": "user",
                                "content": (
                                    f"Analyze this agent prompt and suggest improvements. "
                                    f"Failure patterns: {failure_summary}. "
                                    f"Return only the improved prompt text, no preamble."
                                ),
                            },
                            {"role": "user", "content": original},
                        ],
                        "max_tokens": 4096,
                    },
                )
                if resp.status_code != 200:
                    return ActionResult(success=False, summary=f"Ollama failed: {resp.status_code}")
                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    return ActionResult(success=False, summary="No response from Ollama")
                improved = choices[0].get("message", {}).get("content", "").strip()
                if not improved:
                    return ActionResult(success=False, summary="Empty improved prompt")

            prompt_path.write_text(improved)
            return ActionResult(
                success=True,
                summary=f"Improved prompt for {role}",
                artifacts={"role": role},
            )
        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))


class ImproveHarness(Action):
    """Improve harness entrypoint based on specialist failure analysis."""

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
        return "improve_harness"

    @property
    def category(self) -> str:
        return "code"

    async def estimate_value(self, state: CortexState, perception: Perception) -> float:
        harness_failures = [
            f for f in state.recent_failures
            if "harness" in f.get("summary", "").lower()
            or "specialist" in f.get("summary", "").lower()
        ]
        if harness_failures:
            return 0.6
        return 0.2

    async def execute(self, state: CortexState) -> ActionResult:
        entrypoint = (
            Path(self.repo_path) / "docker" / "claude-harness" / "scripts" / "entrypoint.sh"
        )
        if not entrypoint.exists():
            return ActionResult(success=False, summary=f"Entrypoint not found: {entrypoint}")

        try:
            content = entrypoint.read_text()
            failure_summary = json.dumps(state.recent_failures[-3:], indent=2)[:2000]

            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.ollama_url}/v1/chat/completions",
                    json={
                        "model": "qwen3-coder",
                        "messages": [
                            {
                                "role": "user",
                                "content": (
                                    f"Analyze this harness entrypoint and suggest fixes. "
                                    f"Recent failures: {failure_summary}. "
                                    f"Return only the modified script, no explanation."
                                ),
                            },
                            {"role": "user", "content": content},
                        ],
                        "max_tokens": 4096,
                    },
                )
                if resp.status_code != 200:
                    return ActionResult(success=False, summary=f"Ollama failed: {resp.status_code}")
                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    return ActionResult(success=False, summary="No response from Ollama")
                modified = choices[0].get("message", {}).get("content", "").strip()
                modified = _extract_code_block(modified)
                if not modified:
                    return ActionResult(success=False, summary="Could not extract modified script")

            entrypoint.write_text(modified)
            return ActionResult(
                success=True,
                summary="Updated harness entrypoint",
                artifacts={"path": str(entrypoint)},
            )
        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))


def _extract_code_block(text: str) -> str:
    """Extract content from markdown code block if present."""
    if "```" in text:
        start = text.find("```")
        rest = text[start + 3:]
        if rest.startswith("sh") or rest.startswith("bash"):
            rest = rest[2:].lstrip("\n")
        end_marker = rest.find("```")
        if end_marker >= 0:
            return rest[:end_marker].strip()
        return rest.strip()
    return text.strip()


class FixBug(Action):
    """Fix bug identified from recurring failures."""

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
        return "fix_bug"

    @property
    def category(self) -> str:
        return "code"

    async def estimate_value(self, state: CortexState, perception: Perception) -> float:
        if len(state.recent_failures) >= 3:
            return 0.7
        if state.recent_failures:
            return 0.4
        return 0.1

    async def execute(self, state: CortexState) -> ActionResult:
        if not state.recent_failures:
            return ActionResult(success=False, summary="No recent failures to fix")

        failure_summary = json.dumps(state.recent_failures[-5:], indent=2)[:3000]
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{self.ollama_url}/v1/chat/completions",
                    json={
                        "model": "qwen3-coder",
                        "messages": [
                            {
                                "role": "user",
                                "content": (
                                    "Analyze these OAK builder failures and propose a fix.\n"
                                    f"Failures:\n{failure_summary}\n\n"
                                    "Return a JSON object: "
                                    '{"file": "relative/path", "description": "what to change", '
                                    '"new_content": "full file content"}\n'
                                    "Only suggest changes to files under the oak repo."
                                ),
                            },
                        ],
                        "max_tokens": 4096,
                        "temperature": 0.3,
                    },
                )
                if resp.status_code != 200:
                    return ActionResult(success=False, summary=f"Ollama failed: {resp.status_code}")

                raw = (
                    resp.json()
                    .get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                try:
                    start = raw.index("{")
                    end = raw.rindex("}") + 1
                    change = json.loads(raw[start:end])
                except (ValueError, json.JSONDecodeError):
                    return ActionResult(success=False, summary="Could not parse fix proposal")

                file_path = change.get("file", "")
                description = change.get("description", "")
                return ActionResult(
                    success=True,
                    summary=f"Proposed fix for {file_path}: {description[:100]}",
                    artifacts={"file": file_path, "description": description},
                )
        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))


class AddFeature(Action):
    """Add unimplemented feature from manifest roadmap."""

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
        return "add_feature"

    @property
    def category(self) -> str:
        return "code"

    async def estimate_value(self, state: CortexState, perception: Perception) -> float:
        if state.manifest_delta:
            return 0.5
        return 0.15

    async def execute(self, state: CortexState) -> ActionResult:
        if not state.manifest_delta:
            return ActionResult(success=False, summary="No unimplemented features in manifest")

        feature_name = state.manifest_delta[0] if state.manifest_delta else "unknown"

        manifest_path = Path(self.repo_path) / "manifestv1.0.md"
        if not manifest_path.exists():
            manifest_path = Path(self.repo_path) / "spec.md"
        if not manifest_path.exists():
            return ActionResult(success=False, summary="Manifest not found")

        try:
            manifest_content = manifest_path.read_text()[:4000]
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{self.ollama_url}/v1/chat/completions",
                    json={
                        "model": "qwen3-coder",
                        "messages": [
                            {
                                "role": "user",
                                "content": (
                                    f"Implement the feature: {feature_name}. "
                                    f"Manifest context: {manifest_content}. "
                                    f"Describe what files need to be created/modified "
                                    f"and what each change should do."
                                ),
                            },
                        ],
                        "max_tokens": 2048,
                    },
                )
                if resp.status_code != 200:
                    return ActionResult(success=False, summary=f"Ollama failed: {resp.status_code}")
                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    return ActionResult(success=False, summary="No response from Ollama")
                plan = choices[0].get("message", {}).get("content", "").strip()

            return ActionResult(
                success=True,
                summary=f"Feature plan for {feature_name}: {plan[:150]}",
                artifacts={"feature": feature_name, "plan": plan[:1000]},
            )
        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))
