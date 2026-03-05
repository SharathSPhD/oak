"""Self-modification pipeline: branch -> change -> test -> merge -> rebuild -> signal watchdog."""
from __future__ import annotations

__pattern__ = "Strategy"

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import httpx

from oak_builder.cortex import Action, ActionResult, CortexState, Perception

logger = logging.getLogger("oak.builder.actions.self_modify")


class SelfModify(Action):
    """Full self-modification pipeline.

    1. Identify improvement from audit/failure data
    2. Open git branch
    3. Apply change (prompt, harness, config, or code)
    4. Run acceptance (lint + test)
    5. Merge to main
    6. Rebuild image
    7. Signal watchdog for hot-swap
    """

    name = "self_modify"
    category = "infra"

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

    async def estimate_value(self, state: CortexState, perception: Perception) -> float:
        if len(state.recent_failures) >= 3:
            return 0.7
        if state.cycle_count > 0 and state.cycle_count % 25 == 0:
            return 0.5
        return 0.1

    async def execute(self, state: CortexState) -> ActionResult:
        scope = self._determine_scope(state)
        ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        branch = f"self/{ts}-{scope}"
        worktree_path = f"/oak-builder-wt/{ts}-{scope}"

        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", self.repo_path, "worktree", "add",
                worktree_path, "-b", branch, "main",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                return ActionResult(
                    success=False,
                    summary=f"git worktree add failed: {stderr.decode()[:300]}",
                )

            state.active_branch = branch

            change_result = await self._apply_change(scope, worktree_path, state)
            if not change_result.success:
                await self._cleanup_worktree(worktree_path, branch)
                return change_result

            accept = await self._run_acceptance(worktree_path)
            if not accept["lint"] or not accept["tests"]:
                await self._cleanup_worktree(worktree_path, branch)
                return ActionResult(
                    success=False,
                    summary=f"Acceptance failed: lint={accept['lint']}, tests={accept['tests']}",
                )

            await self._commit_changes(worktree_path, scope)

            merge_ok = await self._merge_to_main(branch)
            if not merge_ok:
                await self._cleanup_worktree(worktree_path, branch)
                return ActionResult(success=False, summary="Merge to main failed")

            await self._cleanup_worktree(worktree_path, branch)

            service = self._scope_to_service(scope)
            if service:
                build_ok = await self._rebuild_and_signal(service, state)
                if build_ok:
                    return ActionResult(
                        success=True,
                        summary=f"Self-modified {scope}, rebuilt {service}, signaled watchdog",
                        artifacts={"branch": branch, "service": service},
                    )

            await self._push_to_remote()

            state.active_branch = ""
            return ActionResult(
                success=True,
                summary=f"Self-modified {scope} and merged to main",
                artifacts={"branch": branch, "scope": scope},
            )

        except Exception as exc:
            logger.exception("Self-modify failed")
            state.active_branch = ""
            return ActionResult(success=False, summary=str(exc))

    def _determine_scope(self, state: CortexState) -> str:
        if state.recent_failures:
            last = state.recent_failures[-1]
            action = last.get("action", "")
            if "prompt" in action:
                return "prompt"
            if "harness" in action or "specialist" in action.lower():
                return "harness"
        return "config"

    async def _apply_change(
        self, scope: str, worktree_path: str, state: CortexState,
    ) -> ActionResult:
        failure_context = ""
        if state.recent_failures:
            failure_context = json.dumps(state.recent_failures[-3:], indent=2)

        prompt = (
            "You are analyzing OAK builder failures to propose a fix.\n"
            f"Scope: {scope}\n"
            f"Recent failures: {failure_context[:2000]}\n\n"
            "Propose a specific, minimal change. Return JSON:\n"
            '{"file": "relative/path", "description": "what to change", '
            '"new_content": "full file content"}'
        )

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{self.ollama_url}/v1/chat/completions",
                    json={
                        "model": "qwen3-coder",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 4096,
                        "temperature": 0.3,
                    },
                )
                if resp.status_code != 200:
                    return ActionResult(
                        success=False,
                        summary=f"Ollama failed: {resp.status_code}",
                    )

                content = (
                    resp.json()
                    .get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )

                try:
                    start = content.index("{")
                    end = content.rindex("}") + 1
                    change = json.loads(content[start:end])
                except (ValueError, json.JSONDecodeError):
                    return ActionResult(
                        success=False,
                        summary="Could not parse LLM response as JSON",
                    )

                target = Path(worktree_path) / change.get("file", "")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(change.get("new_content", ""))

                return ActionResult(
                    success=True,
                    summary=(
                        f"Applied change to {change.get('file')}: "
                        f"{change.get('description', '')}"
                    ),
                )

        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))

    async def _run_acceptance(self, worktree_path: str) -> dict:
        results = {"lint": False, "tests": False}

        proc = await asyncio.create_subprocess_exec(
            "ruff", "check", ".",
            cwd=worktree_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        results["lint"] = proc.returncode == 0

        proc = await asyncio.create_subprocess_exec(
            "pytest", "tests/unit/", "-v", "--tb=short", "-q",
            cwd=worktree_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        results["tests"] = proc.returncode == 0

        return results

    async def _commit_changes(self, worktree_path: str, scope: str) -> None:
        await asyncio.create_subprocess_exec(
            "git", "-C", worktree_path, "add", "-A",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        msg = (
            f"fix({scope}): autonomous self-improvement\n\n"
            "Applied by Cortex self-modify pipeline."
        )
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", worktree_path, "commit", "-m", msg,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

    async def _merge_to_main(self, branch: str) -> bool:
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", self.repo_path, "checkout", "main",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if proc.returncode != 0:
            return False

        proc = await asyncio.create_subprocess_exec(
            "git", "-C", self.repo_path, "merge", branch, "--no-edit",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return proc.returncode == 0

    async def _cleanup_worktree(self, worktree_path: str, branch: str) -> None:
        await asyncio.create_subprocess_exec(
            "git", "-C", self.repo_path, "worktree", "remove",
            worktree_path, "--force",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.create_subprocess_exec(
            "git", "-C", self.repo_path, "branch", "-D", branch,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    def _scope_to_service(self, scope: str) -> str:
        mapping = {
            "harness": "claude-harness",
            "config": "api",
            "builder": "builder",
        }
        return mapping.get(scope, "")

    async def _rebuild_and_signal(
        self, service: str, state: CortexState,
    ) -> bool:
        version = state.cycle_count
        tag = f"oak/{service}:self-v{version}"

        dockerfile = Path(self.repo_path) / "docker" / service / "Dockerfile"
        if not dockerfile.exists():
            return False

        proc = await asyncio.create_subprocess_exec(
            "docker", "build", "-t", tag, "-f", str(dockerfile), ".",
            cwd=self.repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error("Docker build failed: %s", stderr.decode()[:500])
            return False

        signals_dir = Path("/watchdog/signals")
        signals_dir.mkdir(parents=True, exist_ok=True)
        signal = {
            "service": service,
            "new_image": tag,
            "handover_state": str(
                Path(self.workspace_base) / "builder" / "cortex_state.json"
            ),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        (signals_dir / "replace.json").write_text(
            json.dumps(signal, indent=2)
        )
        logger.info("Signaled watchdog: %s -> %s", service, tag)
        return True

    async def _push_to_remote(self) -> None:
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", self.repo_path, "push", "origin", "main",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning("Push failed: %s", stderr.decode()[:300])
