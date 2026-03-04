__pattern__ = "Observer"

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.dependencies import get_event_bus
from api.routers import agents, judge, problems, skills, tasks, telemetry
from api.routers.mailbox import router as mailbox_router
from api.ws import stream


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    get_event_bus()  # Register EventBus subscribers on startup
    yield


app = FastAPI(
    title="OAK API",
    description="Orchestrated Agent Kernel -- TRUNK layer",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(problems.router)
app.include_router(tasks.router)
app.include_router(agents.router)
app.include_router(skills.router)
app.include_router(telemetry.router)
app.include_router(judge.router)
app.include_router(mailbox_router)
app.include_router(stream.router)



@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "healthy",
        "oak_mode": settings.oak_mode,
        "routing_strategy": settings.routing_strategy,
        "stall_detection_enabled": settings.stall_detection_enabled,
        "max_agents_per_problem": settings.max_agents_per_problem,
        "max_concurrent_problems": settings.max_concurrent_problems,
        "models": {
            "default": settings.default_model,
            "coder": settings.coder_model,
            "analysis": settings.analysis_model,
        },
        "feature_flags": {
            "telemetry_enabled": settings.telemetry_enabled,
            "skill_extraction_enabled": settings.skill_extraction_enabled,
            "judge_required": settings.judge_required,
            "meta_agent_enabled": settings.meta_agent_enabled,
        },
        "api_key_present": bool(settings.anthropic_api_key_real),
    }


@app.post("/internal/events")
async def receive_event(request: Request) -> dict[str, str]:
    """Hook relay endpoint. Receives AgentEvent from post-tool-use.sh and publishes to EventBus."""
    from api.events.bus import AgentEvent as BusEvent
    body = await request.json()
    bus = get_event_bus()
    await bus.publish(BusEvent(
        event_type=body.get("event_type", "unknown"),
        agent_id=body.get("agent_id", "unknown"),
        problem_uuid=body.get("problem_uuid", "unknown"),
        timestamp_utc=body.get("timestamp_utc", 0.0),
        payload=body.get("payload", {}),
    ))
    return {"status": "ok"}
