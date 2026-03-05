"""Infrastructure actions: rebuild images, update/add dependencies."""
from __future__ import annotations

__pattern__ = "Strategy"

import asyncio
import json
import logging
from pathlib import Path

import httpx

from oak_builder.cortex import Action, ActionResult, CortexState, Perception

logger = logging.getLogger("oak.builder.actions.infra")


class RebuildImage(Action):
    """Rebuild Docker image, smoke test, and signal watchdog to replace."""

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
        return "rebuild_image"

    @property
    def category(self) -> str:
        return "infra"

    async def estimate_value(self, state: CortexState, perception: Perception) -> float:
        if state.get("image_rebuild_needed"):
            return 0.9
        if state.get("code_changed"):
            return 0.6
        return 0.2

    async def execute(self, state: CortexState) -> ActionResult:
        service = state.get("service", "api")
        version = state.get("image_version", 1)
        tag = f"oak/{service}:self-v{version}"

        dockerfile_dir = Path(self.repo_path) / "docker" / service
        dockerfile = dockerfile_dir / "Dockerfile"
        if not dockerfile.exists():
            dockerfile = Path(self.repo_path) / "docker" / f"{service}" / "Dockerfile"
        if not dockerfile.exists():
            return ActionResult(success=False, summary=f"Dockerfile not found for {service}")

        try:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "build",
                "-t",
                tag,
                "-f",
                str(dockerfile),
                ".",
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                return ActionResult(
                    success=False,
                    summary=f"docker build failed: {stderr.decode()[:500]}",
                )

            smoke_ok = await _smoke_test(service, self.api_url)
            if not smoke_ok:
                return ActionResult(
                    success=False,
                    summary="Smoke test failed after rebuild",
                    artifacts={"tag": tag},
                )

            signals_dir = Path("/watchdog/signals")
            signals_dir.mkdir(parents=True, exist_ok=True)
            replace_signal = {
                "action": "REPLACE",
                "service": service,
                "image": tag,
            }
            (signals_dir / "replace.json").write_text(json.dumps(replace_signal))
            logger.info("Rebuilt %s, wrote replace signal", tag)
            return ActionResult(
                success=True,
                artifacts={"tag": tag, "signal": "replace.json"},
            )
        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))


async def _smoke_test(service: str, api_url: str) -> bool:
    """Run minimal smoke test for the service."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{api_url}/health")
            return resp.status_code == 200
    except Exception:
        return False


class UpdateDependency(Action):
    """Read requirements, check for updates, modify, rebuild, test."""

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
        return "update_dependency"

    @property
    def category(self) -> str:
        return "infra"

    async def estimate_value(self, state: CortexState, perception: Perception) -> float:
        if state.get("dependencies_outdated"):
            return 0.8
        return 0.3

    async def execute(self, state: CortexState) -> ActionResult:
        req_file = Path(self.repo_path) / "requirements.txt"
        if not req_file.exists():
            req_file = Path(self.repo_path) / "pyproject.toml"
        if not req_file.exists():
            return ActionResult(success=False, summary="No requirements.txt or pyproject.toml")

        try:
            content = req_file.read_text()
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
                                    "Check requirements for outdated packages. "
                                    "Return the updated requirements content only, "
                                    "with version bumps for security/minor updates. "
                                    "Keep the same format."
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
                updated = choices[0].get("message", {}).get("content", "").strip()
                if "```" in updated:
                    start = updated.find("\n") + 1
                    end = updated.rfind("```")
                    if end > start:
                        updated = updated[start:end].strip()

            req_file.write_text(updated)
            proc = await asyncio.create_subprocess_exec(
                "pytest",
                "tests/unit/",
                "-v",
                "--tb=short",
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            if proc.returncode != 0:
                return ActionResult(
                    success=False,
                    summary="Tests failed after dependency update",
                    artifacts={"file": str(req_file)},
                )
            logger.info("Updated dependencies in %s", req_file)
            return ActionResult(success=True, artifacts={"file": str(req_file)})
        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))


class AddDependency(Action):
    """Add a package to requirements, rebuild, test."""

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
        return "add_dependency"

    @property
    def category(self) -> str:
        return "infra"

    async def estimate_value(self, state: CortexState, perception: Perception) -> float:
        if state.get("dependency_to_add"):
            return 0.8
        return 0.3

    async def execute(self, state: CortexState) -> ActionResult:
        package = state.get("dependency_to_add")
        if not package:
            return ActionResult(success=False, summary="No dependency_to_add in state")

        req_file = Path(self.repo_path) / "requirements.txt"
        if not req_file.exists():
            return ActionResult(success=False, summary="requirements.txt not found")

        try:
            content = req_file.read_text()
            if package.split("==")[0].split("[")[0].lower() in [
                line.split("==")[0].split("[")[0].lower() for line in content.splitlines()
            ]:
                return ActionResult(
                    success=True,
                    artifacts={"message": f"{package} already present"},
                )

            new_line = f"{package}\n"
            req_file.write_text(content.rstrip() + "\n" + new_line)

            proc = await asyncio.create_subprocess_exec(
                "pip",
                "install",
                "-r",
                str(req_file),
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            if proc.returncode != 0:
                return ActionResult(
                    success=False,
                    summary=f"pip install failed for {package}",
                )

            proc = await asyncio.create_subprocess_exec(
                "pytest",
                "tests/unit/",
                "-v",
                "--tb=short",
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            if proc.returncode != 0:
                return ActionResult(
                    success=False,
                    summary="Tests failed after adding dependency",
                )
            logger.info("Added dependency %s", package)
            return ActionResult(success=True, artifacts={"package": package})
        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))
