__pattern__ = "Factory"

from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends

from api.dependencies import get_settings
from api.config import OAKSettings
from api.models import AgentStatusResponse

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.post("/spawn")
async def spawn_agent(
    role: str,
    problem_uuid: UUID,
    settings: OAKSettings = Depends(get_settings),
):
    """Spawn an agent for a problem via AgentFactory. Returns container ID."""
    raise HTTPException(status_code=501, detail="Phase 1: not yet implemented")


@router.get("/status", response_model=list[AgentStatusResponse])
async def get_agents_status() -> list[AgentStatusResponse]:
    """Returns status of all active agent sessions. Phase 0: always empty."""
    return []
