__pattern__ = "Factory"

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from api.config import OAKSettings
from api.dependencies import get_settings

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.post("/spawn")
async def spawn_agent(
    role: str,
    problem_uuid: UUID,
    settings: OAKSettings = Depends(get_settings),
) -> dict[str, str]:
    """Spawn an agent for a problem via DGXAgentFactory. Returns container ID."""
    from api.factories.agent_factory import DGXAgentFactory, ResourceCapExceededError
    from api.services.agent_registry import AgentRegistry

    registry = AgentRegistry(str(settings.redis_url))
    all_agents = await registry.get_all()

    # Enforce MAX_HARNESS_CONTAINERS
    if len(all_agents) >= settings.max_harness_containers:
        raise HTTPException(
            status_code=503,
            detail=f"MAX_HARNESS_CONTAINERS ({settings.max_harness_containers}) reached",
        )

    # Enforce MAX_AGENTS_PER_PROBLEM
    agents_for_problem = [a for a in all_agents if a.problem_uuid == str(problem_uuid)]
    if len(agents_for_problem) >= settings.max_agents_per_problem:
        raise HTTPException(
            status_code=503,
            detail=(
                f"MAX_AGENTS_PER_PROBLEM ({settings.max_agents_per_problem}) "
                f"reached for {problem_uuid}"
            ),
        )

    # Enforce MAX_CONCURRENT_PROBLEMS (only if this is a new problem)
    active_problems = {a.problem_uuid for a in all_agents if a.problem_uuid}
    if (
        str(problem_uuid) not in active_problems
        and len(active_problems) >= settings.max_concurrent_problems
    ):
        raise HTTPException(
            status_code=503,
            detail=f"MAX_CONCURRENT_PROBLEMS ({settings.max_concurrent_problems}) reached",
        )

    try:
        factory = DGXAgentFactory()
        spec = factory.create(role, str(problem_uuid))
        spec.model = settings.model_for_role(role)
        container_id = factory.launch(spec)
        await registry.register(spec.agent_id, role, str(problem_uuid), container_id)
        return {"agent_id": spec.agent_id, "container_id": container_id, "role": role,
                "model": spec.model}
    except ResourceCapExceededError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.get("/status")
async def get_agents_status(
    settings: OAKSettings = Depends(get_settings),
) -> list[dict[str, Any]]:
    """Return status of all running agents from registry."""
    from api.services.agent_registry import AgentRegistry
    registry = AgentRegistry(str(settings.redis_url))
    agents = await registry.get_all()
    return [a.model_dump() for a in agents]


@router.get("/models")
async def get_models(settings: OAKSettings = Depends(get_settings)) -> dict[str, Any]:
    """List configured Ollama models and their role assignments."""
    return {
        "models": {
            "coder": settings.coder_model,
            "analysis": settings.analysis_model,
            "reasoning": settings.reasoning_model,
            "default": settings.default_model,
        },
        "role_routing": {
            "data-engineer": settings.coder_model,
            "ml-engineer": settings.coder_model,
            "data-scientist": settings.analysis_model,
            "skill-extractor": settings.analysis_model,
            "orchestrator": settings.reasoning_model,
            "judge-agent": settings.reasoning_model,
            "meta-agent": settings.reasoning_model,
            "software-architect": settings.reasoning_model,
        },
    }
