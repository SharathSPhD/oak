__pattern__ = "Observer"

import asyncpg
from fastapi import APIRouter, HTTPException

from api.config import settings
from api.models import TelemetryEventCreate, TelemetryResponse

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


@router.get("", response_model=TelemetryResponse)
async def get_telemetry():
    """Return aggregated telemetry metrics from agent_telemetry table."""
    conn = await asyncpg.connect(settings.database_url)
    try:
        total_row = await conn.fetchrow("SELECT COUNT(*) as cnt FROM agent_telemetry")
        total_events = total_row["cnt"] if total_row else 0

        escalation_row = await conn.fetchrow(
            "SELECT COUNT(*) as cnt FROM agent_telemetry WHERE escalated = TRUE"
        )
        total_escalations = escalation_row["cnt"] if escalation_row else 0

        escalation_rate = (
            round(total_escalations / total_events * 100, 1) if total_events > 0 else 0.0
        )

        type_rows = await conn.fetch(
            "SELECT event_type, COUNT(*) as cnt FROM agent_telemetry GROUP BY event_type"
        )
        events_by_type = {r["event_type"]: r["cnt"] for r in type_rows}

        active_problems_row = await conn.fetchrow(
            "SELECT COUNT(DISTINCT problem_id) as cnt FROM agent_telemetry "
            "WHERE created_at > NOW() - INTERVAL '1 hour'"
        )
        active_problems = active_problems_row["cnt"] if active_problems_row else 0

        recent_rows = await conn.fetch(
            "SELECT id, agent_id, event_type, tool_name, escalated, created_at "
            "FROM agent_telemetry ORDER BY created_at DESC LIMIT 20"
        )
        recent_events = [
            {
                "id": str(r["id"]),
                "agent_id": r["agent_id"],
                "event_type": r["event_type"],
                "tool_name": r["tool_name"],
                "escalated": r["escalated"],
                "created_at": str(r["created_at"]),
            }
            for r in recent_rows
        ]

        return TelemetryResponse(
            total_events=total_events,
            total_escalations=total_escalations,
            escalation_rate_pct=escalation_rate,
            events_by_type=events_by_type,
            active_problems=active_problems,
            recent_events=recent_events,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        await conn.close()


@router.post("", status_code=201)
async def record_event(event: TelemetryEventCreate):
    """Record a telemetry event from an agent hook (post-tool-use.sh)."""
    conn = await asyncpg.connect(settings.database_url)
    try:
        import json
        row = await conn.fetchrow(
            """INSERT INTO agent_telemetry
               (problem_id, agent_id, event_type, tool_name, tool_input, tool_response,
                duration_ms, escalated)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
               RETURNING id, created_at""",
            event.problem_id,
            event.agent_id,
            event.event_type,
            event.tool_name,
            json.dumps(event.tool_input) if event.tool_input else None,
            json.dumps(event.tool_response) if event.tool_response else None,
            event.duration_ms,
            event.escalated,
        )
        return {"id": str(row["id"]), "created_at": str(row["created_at"])}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        await conn.close()
