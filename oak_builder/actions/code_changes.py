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
    """Improve agent prompt based on audit_self failure patterns."""

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
        audit = state.get("audit_self", {})
        failures = audit.get("failure_patterns", {})
        if failures and any(f.get("role") for f in failures.values() if isinstance(f, dict)):
            return 0.9
        if failures:
            return 0.6
        return 0.2

    async def execute(self, state: CortexState) -> ActionResult:
        audit = state.get("audit_self", {})
        failure_patterns = audit.get("failure_patterns", {})
        roles = set()
        for v in failure_patterns.values():
            if isinstance(v, dict) and v.get("role"):
                roles.add(v["role"])
        role = next(iter(roles), None) or "data-engineer"

        prompt_path = Path(self.repo_path) / ".claude" / "agents" / f"{role}.md"
        if not prompt_path.exists():
            return ActionResult(success=False, summary=f"Agent prompt not found: {prompt_path}")

        try:
            original = prompt_path.read_text()
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.ollama_url}/v1/chat/completions",
                    headers={"Authorization": "Bearer ollama"},
                    json={
                        "model": "qwen3-coder",
                        "messages": [
                            {
                                "role": "user",
                                "content": (
                                    f"Analyze this agent prompt and suggest improvements. "
                                    f"Failure patterns: {failure_patterns}. "
                                    f"Return only the improved prompt text, no preamble."
                                ),
                            },
                            {"role": "user", "content": original},
                        ],
                        "stream": False,
                    },
                )
                if resp.status_code != 200:
                    return ActionResult(
                        success=False,
                        summary=f"Ollama request failed: {resp.status_code}",
                    )
                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    return ActionResult(success=False, summary="No response from Ollama")
                improved = choices[0].get("message", {}).get("content", "").strip()
                if not improved:
                    return ActionResult(success=False, summary="Empty improved prompt")

            prompt_path.write_text(improved)
            logger.info("Updated prompt for role %s", role)

            test_result = await _run_test_problem(self.api_url)
            return ActionResult(
                success=test_result.get("passed", False),
                artifacts={
                    "role": role,
                    "test_passed": test_result.get("passed"),
                    "judge_score": test_result.get("judge_score"),
                },
                summary=(
                    None
                    if test_result.get("passed")
                    else "Test problem failed after prompt change"
                ),
            )
        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))


async def _run_test_problem(api_url: str) -> dict[str, Any]:
    """Run a minimal test problem to validate changes."""
    try:
        async with httpx.AsyncClient(base_url=api_url, timeout=90) as client:
            resp = await client.post(
                "/api/problems",
                json={"title": "Prompt validation", "description": "Minimal ETL test"},
            )
            if resp.status_code != 200:
                return {"passed": False}
            problem_id = resp.json().get("id")
            if not problem_id:
                return {"passed": False}
            await asyncio.sleep(60)
            v = await client.get(f"/api/problems/{problem_id}/verdict")
            if v.status_code != 200:
                return {"passed": False}
            data = v.json()
            return {"passed": data.get("verdict") == "pass", "judge_score": data.get("score")}
    except Exception:
        return {"passed": False}


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
        failures = state.get("failure_analysis", {})
        if failures.get("harness_related"):
            return 0.75
        if failures.get("specialist_failures"):
            return 0.5
        return 0.2

    async def execute(self, state: CortexState) -> ActionResult:
        entrypoint = (
            Path(self.repo_path) / "docker" / "claude-harness" / "scripts" / "entrypoint.sh"
        )
        if not entrypoint.exists():
            return ActionResult(success=False, summary=f"Entrypoint not found: {entrypoint}")

        try:
            content = entrypoint.read_text()
            failure_analysis = state.get("failure_analysis", {})

            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.ollama_url}/v1/chat/completions",
                    headers={"Authorization": "Bearer ollama"},
                    json={
                        "model": "qwen3-coder",
                        "messages": [
                            {
                                "role": "user",
                                "content": (
                                    f"Analyze this harness entrypoint and suggest fixes. "
                                    f"Failure analysis: {failure_analysis}. "
                                    f"Return only the modified script, no explanation."
                                ),
                            },
                            {"role": "user", "content": content},
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
                modified = choices[0].get("message", {}).get("content", "").strip()
                if not modified or "```" in modified[:50]:
                    modified = _extract_code_block(modified)
                if not modified:
                    return ActionResult(success=False, summary="Could not extract modified script")

            entrypoint.write_text(modified)
            logger.info("Updated harness entrypoint")
            return ActionResult(success=True, artifacts={"path": str(entrypoint)})
        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))


def _extract_code_block(text: str) -> str:
    """Extract content from markdown code block if present."""
    if "```" in text:
        start = text.find("```")
        rest = text[start + 3:]
        if rest.startswith("sh") or rest.startswith("bash"):
            rest = rest[2:].lstrip("\n")
        end = rest.find("```")
        if end >= 0:
            return rest[:end].strip()
        return rest.strip()
    return text.strip()


class FixBug(Action):
    """Fix bug identified from telemetry recurring errors."""

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
        telemetry = state.get("telemetry", {})
        errors = telemetry.get("recurring_errors", [])
        if len(errors) >= 2:
            return 0.9
        if errors:
            return 0.6
        return 0.2

    async def execute(self, state: CortexState) -> ActionResult:
        telemetry = state.get("telemetry", {})
        errors = telemetry.get("recurring_errors", [])
        if not errors:
            return ActionResult(success=False, summary="No recurring errors in telemetry")

        error_info = errors[0] if isinstance(errors[0], dict) else {"message": str(errors[0])}
        source_file = error_info.get("source_file") or _infer_source_from_error(error_info)

        if not source_file:
            return ActionResult(success=False, summary="Could not identify source file")

        file_path = Path(self.repo_path) / source_file.lstrip("/")
        if not file_path.exists():
            return ActionResult(success=False, summary=f"Source file not found: {file_path}")

        try:
            content = file_path.read_text()
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.ollama_url}/v1/chat/completions",
                    headers={"Authorization": "Bearer ollama"},
                    json={
                        "model": "qwen3-coder",
                        "messages": [
                            {
                                "role": "user",
                                "content": (
                                    f"Fix this bug. Error: {error_info}. "
                                    f"Return only the fixed file content, no explanation."
                                ),
                            },
                            {"role": "user", "content": content},
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
                fixed = choices[0].get("message", {}).get("content", "").strip()
                fixed = _extract_code_block(fixed)

            file_path.write_text(fixed)
            logger.info("Applied fix to %s", source_file)

            proc = await asyncio.create_subprocess_exec(
                "pytest", "tests/unit/", "-v", "--tb=short",
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            passed = proc.returncode == 0
            return ActionResult(
                success=passed,
                artifacts={"file": source_file, "tests_passed": passed},
                summary=None if passed else stderr.decode()[:500],
            )
        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))


def _infer_source_from_error(error_info: dict) -> str | None:
    """Infer source file from error message or stack trace."""
    msg = str(error_info.get("message", ""))
    for prefix in ("api/", "memory/", "oak_mcp/"):
        if prefix in msg:
            parts = msg.split(prefix, 1)[1].split(":", 1)[0].split()
            if parts:
                return prefix + parts[0]
    return None


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
        gaps = state.get("manifest_roadmap_gaps", [])
        if gaps:
            return 0.65
        return 0.2

    async def execute(self, state: CortexState) -> ActionResult:
        gaps = state.get("manifest_roadmap_gaps", [])
        if not gaps:
            return ActionResult(success=False, summary="No unimplemented features in manifest")

        manifest_path = Path(self.repo_path) / "manifestv1.0.md"
        if not manifest_path.exists():
            manifest_path = Path(self.repo_path) / "spec.md"
        if not manifest_path.exists():
            return ActionResult(success=False, summary="Manifest not found")

        feature = gaps[0] if isinstance(gaps[0], dict) else {"name": str(gaps[0]), "priority": 1}
        feature_name = feature.get("name", "unknown")

        try:
            manifest_content = manifest_path.read_text()
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{self.ollama_url}/v1/chat/completions",
                    headers={"Authorization": "Bearer ollama"},
                    json={
                        "model": "qwen3-coder",
                        "messages": [
                            {
                                "role": "user",
                                "content": (
                                    f"Implement the feature: {feature_name}. "
                                    f"Manifest context: {manifest_content[:4000]}. "
                                    f"Return file paths and their full content as a JSON object: "
                                    f'{{"files": [{{"path": "...", "content": "..."}}]}}'
                                ),
                            },
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
                raw = choices[0].get("message", {}).get("content", "").strip()
                raw = _extract_json_from_response(raw)

            parsed = json.loads(raw)
            files = parsed.get("files", [])
            if not files:
                return ActionResult(success=False, summary="No files in response")

            for f in files[:5]:
                path = Path(self.repo_path) / f.get("path", "").lstrip("/")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f.get("content", ""))

            logger.info("Added feature %s: %d files", feature_name, len(files))
            return ActionResult(
                success=True,
                artifacts={"feature": feature_name, "files": [f.get("path") for f in files]},
            )
        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))


def _extract_json_from_response(text: str) -> str:
    """Extract JSON object from LLM response."""
    text = text.strip()
    if text.startswith("```"):
        start = text.find("{")
        if start >= 0:
            end = text.rfind("}") + 1
            if end > start:
                return text[start:end]
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        start = text.find("{")
        if start >= 0:
            depth = 0
            for i, c in enumerate(text[start:], start):
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        return text[start : i + 1]
    return text
