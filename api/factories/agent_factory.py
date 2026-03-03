"""AgentFactory implementations for launching harness containers."""
__pattern__ = "Factory"

import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from uuid import uuid4


class ResourceCapExceeded(Exception):
    """Raised when Docker refuses to start a container."""


@dataclass
class AgentSpec:
    """Container spec produced by AgentFactory.create()."""
    agent_id: str
    role: str
    problem_uuid: str
    harness_image: str = "oak/harness:latest"
    resource_limits: dict = field(default_factory=lambda: {"memory": "4g", "cpus": "2.0"})


class AgentFactory(ABC):
    """Abstract factory for agent session creation."""

    @abstractmethod
    def create(self, role: str, problem_uuid: str) -> AgentSpec:
        """Produce an agent spec; does not launch the container."""

    @abstractmethod
    def launch(self, spec: AgentSpec) -> str:
        """Launch the harness container; return container ID."""


class DGXAgentFactory(AgentFactory):
    """Concrete factory for DGX Spark profile."""

    def create(self, role: str, problem_uuid: str) -> AgentSpec:
        return AgentSpec(agent_id=str(uuid4()), role=role, problem_uuid=problem_uuid)

    def launch(self, spec: AgentSpec) -> str:
        cmd = [
            "docker", "run", "-d",
            "--name", spec.agent_id,
            "--memory", spec.resource_limits.get("memory", "4g"),
            "--cpus", spec.resource_limits.get("cpus", "2.0"),
            "-e", f"OAK_AGENT_ID={spec.agent_id}",
            "-e", f"OAK_PROBLEM_UUID={spec.problem_uuid}",
            "-e", f"OAK_ROLE={spec.role}",
            "-e", "ANTHROPIC_BASE_URL=http://oak-api-proxy:9000",
            "-e", "ANTHROPIC_AUTH_TOKEN=ollama",
            spec.harness_image,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise ResourceCapExceeded(result.stderr.strip())
        return result.stdout.strip()


class MiniAgentFactory(AgentFactory):
    """Concrete factory for Mac Mini M4 profile. Phase 4."""

    def create(self, role: str, problem_uuid: str) -> AgentSpec:
        raise NotImplementedError("Phase 4")

    def launch(self, spec: AgentSpec) -> str:
        raise NotImplementedError("Phase 4")


class CloudAgentFactory(AgentFactory):
    """Concrete factory for cloud GPU profile. Phase 5."""

    def create(self, role: str, problem_uuid: str) -> AgentSpec:
        raise NotImplementedError("Phase 5")

    def launch(self, spec: AgentSpec) -> str:
        raise NotImplementedError("Phase 5")
