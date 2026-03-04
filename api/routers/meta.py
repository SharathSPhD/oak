__pattern__ = "Repository"

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from api.config import OAKSettings
from api.dependencies import get_settings

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/proposals")
async def list_proposals(
    settings: OAKSettings = Depends(get_settings),
) -> dict[str, Any]:
    """Return the latest meta-agent proposals from all problem workspaces."""
    base = Path(settings.oak_workspace_base)
    proposals: list[dict[str, Any]] = []

    if base.exists():
        for ws in sorted(base.iterdir()):
            fp = ws / "meta_proposals.json"
            if fp.is_file():
                try:
                    data = json.loads(fp.read_text())
                    proposals.append({
                        "workspace": ws.name,
                        "proposals": data,
                    })
                except (json.JSONDecodeError, OSError):
                    pass

    return {"count": len(proposals), "proposals": proposals}


@router.post("/apply-proposals")
async def apply_proposals(
    settings: OAKSettings = Depends(get_settings),
) -> dict[str, Any]:
    """Read meta_proposals.json from the daemon workspace and store for review.

    Full auto-application is out of scope for safety. This endpoint makes
    proposals queryable and logs them for human review.
    """
    daemon_ws = Path(settings.oak_workspace_base) / "daemon"
    fp = daemon_ws / "meta_proposals.json"

    if not fp.is_file():
        return {"status": "no_proposals", "message": "No meta_proposals.json found"}

    try:
        data = json.loads(fp.read_text())
    except (json.JSONDecodeError, OSError):
        return {"status": "error", "message": "Failed to parse meta_proposals.json"}

    proposal_list = data.get("proposals", []) if isinstance(data, dict) else []

    return {
        "status": "reviewed",
        "proposal_count": len(proposal_list),
        "proposals": proposal_list,
        "message": "Proposals loaded for review. Auto-application disabled for safety.",
    }
