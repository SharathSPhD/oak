"""Git operations: open branch, PR review, acceptance, merge, push."""
from __future__ import annotations

__pattern__ = "Strategy"

import asyncio
import json
import logging
from datetime import UTC, datetime

import httpx

from oak_builder.cortex import Action, ActionResult, CortexState, Perception

logger = logging.getLogger("oak.builder.actions.git_ops")


class OpenBranch(Action):
    """Create a new worktree and branch for self-build changes."""

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
        return "open_branch"

    @property
    def category(self) -> str:
        return "git"

    async def estimate_value(self, state: CortexState, perception: Perception) -> float:
        if getattr(state, "needs_branch", None) or not getattr(state, "current_branch", None):
            return 0.8
        return 0.3

    async def execute(self, state: CortexState) -> ActionResult:
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M")
        scope = getattr(state, "scope", "self-build")
        worktree_path = f"/oak-builder-wt/self-{timestamp}-{scope}"
        branch_name = f"self/{timestamp}-{scope}"

        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                self.repo_path,
                "worktree",
                "add",
                worktree_path,
                "-b",
                branch_name,
                "main",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                return ActionResult(
                    success=False,
                    summary=f"git worktree add failed: {stderr.decode()[:300]}",
                )
            logger.info("Opened branch %s at %s", branch_name, worktree_path)
            return ActionResult(
                success=True,
                artifacts={
                    "branch": branch_name,
                    "worktree_path": worktree_path,
                },
            )
        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))


class PrReview(Action):
    """Get diff of current branch vs main and send to Ollama for review."""

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
        return "pr_review"

    @property
    def category(self) -> str:
        return "git"

    async def estimate_value(self, state: CortexState, perception: Perception) -> float:
        if getattr(state, "pending_review", None):
            return 0.9
        return 0.4

    async def execute(self, state: CortexState) -> ActionResult:
        worktree = getattr(state, "worktree_path", self.repo_path)
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                worktree,
                "diff",
                "main",
                "--no-color",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                return ActionResult(
                    success=False,
                    summary=f"git diff failed: {stderr.decode()[:300]}",
                )
            diff = stdout.decode()

            if not diff.strip():
                return ActionResult(
                    success=True,
                    artifacts={"approved": True, "reason": "No changes to review"},
                )

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
                                    "Review this diff. Reply with a JSON object: "
                                    '{"approved": true|false, "reason": "brief explanation"}'
                                ),
                            },
                            {"role": "user", "content": f"```diff\n{diff[:12000]}\n```"},
                        ],
                        "stream": False,
                    },
                )
                if resp.status_code != 200:
                    return ActionResult(
                        success=False,
                        summary=f"Ollama review failed: {resp.status_code}",
                    )
                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    return ActionResult(success=False, summary="No response from Ollama")
                raw = choices[0].get("message", {}).get("content", "").strip()
                raw = _extract_json(raw)
                parsed = json.loads(raw)
                approved = parsed.get("approved", False)
                reason = parsed.get("reason", "")

            return ActionResult(
                success=True,
                artifacts={"approved": approved, "reason": reason},
            )
        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))


def _extract_json(text: str) -> str:
    """Extract JSON from response."""
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


class RunAcceptance(Action):
    """Run acceptance tiers: ruff + pytest, judge score, regression."""

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
        return "run_acceptance"

    @property
    def category(self) -> str:
        return "git"

    async def estimate_value(self, state: CortexState, perception: Perception) -> float:
        if getattr(state, "acceptance_pending", None):
            return 0.95
        return 0.5

    async def execute(self, state: CortexState) -> ActionResult:
        worktree = getattr(state, "worktree_path", self.repo_path)
        results: dict[str, bool] = {}

        try:
            proc = await asyncio.create_subprocess_exec(
                "ruff",
                "check",
                "api/",
                "memory/",
                "oak_mcp/",
                cwd=worktree,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            results["tier1_ruff"] = proc.returncode == 0

            proc = await asyncio.create_subprocess_exec(
                "pytest",
                "tests/unit/",
                "-v",
                "--tb=short",
                cwd=worktree,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            results["tier1_pytest"] = proc.returncode == 0

            results["tier2_judge"] = False
            if getattr(state, "problem_id", None):
                async with httpx.AsyncClient(base_url=self.api_url, timeout=30) as client:
                    v = await client.get(f"/api/problems/{getattr(state, 'problem_id', None)}/verdict")
                    if v.status_code == 200:
                        data = v.json()
                        results["tier2_judge"] = data.get("verdict") == "pass"

            results["tier3_regression"] = results["tier1_ruff"] and results["tier1_pytest"]

            passed = all(results.values())
            return ActionResult(
                success=passed,
                artifacts={"tiers": results},
                summary=None if passed else f"Tiers: {results}",
            )
        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))


class MergeToMain(Action):
    """Merge current branch to main and clean up worktree if acceptance passed."""

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
        return "merge_to_main"

    @property
    def category(self) -> str:
        return "git"

    async def estimate_value(self, state: CortexState, perception: Perception) -> float:
        if getattr(state, "acceptance_passed", None) and getattr(state, "branch", None):
            return 0.9
        return 0.3

    async def execute(self, state: CortexState) -> ActionResult:
        acceptance = getattr(state, "acceptance_tiers", {})
        if not all(acceptance.values()) if acceptance else True:
            return ActionResult(success=False, summary="Acceptance must pass before merge")

        worktree = getattr(state, "worktree_path", None)
        branch = getattr(state, "branch", "self/unknown")

        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                self.repo_path,
                "checkout",
                "main",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            if proc.returncode != 0:
                return ActionResult(success=False, summary="Failed to checkout main")

            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                self.repo_path,
                "merge",
                branch,
                "--no-edit",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                return ActionResult(
                    success=False,
                    summary=f"Merge failed: {stderr.decode()[:300]}",
                )

            if worktree:
                proc = await asyncio.create_subprocess_exec(
                    "git",
                    "-C",
                    self.repo_path,
                    "worktree",
                    "remove",
                    worktree,
                    "--force",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
                proc = await asyncio.create_subprocess_exec(
                    "git",
                    "-C",
                    self.repo_path,
                    "branch",
                    "-d",
                    branch,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()

            logger.info("Merged %s to main", branch)
            return ActionResult(success=True, artifacts={"merged_branch": branch})
        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))


class PushToRemote(Action):
    """Push main to origin via SSH."""

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
        return "push_to_remote"

    @property
    def category(self) -> str:
        return "git"

    async def estimate_value(self, state: CortexState, perception: Perception) -> float:
        if getattr(state, "merge_complete", None) and getattr(state, "push_pending", None):
            return 0.9
        return 0.4

    async def execute(self, state: CortexState) -> ActionResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                self.repo_path,
                "push",
                "origin",
                "main",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                return ActionResult(
                    success=False,
                    summary=f"git push failed: {stderr.decode()[:300]}",
                )
            logger.info("Pushed main to origin")
            return ActionResult(success=True, artifacts={"pushed": "main"})
        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))
