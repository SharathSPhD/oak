"""
oak-api-proxy: Routes Claude Code API calls to Ollama or Claude API.
Implements the OAK Harness Proxy layer (HARNESS PROXY in architecture).
Never modifies the proxy() function — all routing logic lives in RoutingStrategy subclasses.
"""
__pattern__ = "Strategy"

import os
import httpx
import json
import redis as _redis_sync
from fastapi import FastAPI, Request, Response
from strategies import (
    PassthroughStrategy, StallDetectionStrategy, ConfidenceThresholdStrategy, RoutingStrategy
)

app = FastAPI(title="OAK API Proxy", version="0.1.0")

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://oak-ollama:11434")
ANTHROPIC_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_API_KEY_REAL = os.environ.get("ANTHROPIC_API_KEY_REAL", "")
ROUTING_STRATEGY_NAME = os.environ.get("ROUTING_STRATEGY", "passthrough")
STALL_DETECTION_ENABLED = os.environ.get("STALL_DETECTION_ENABLED", "false").lower() == "true"
STALL_MIN_TOKENS = int(os.environ.get("STALL_MIN_TOKENS", "20"))

# Build routing strategy from config — never use inline conditionals (PRD AP-2)
_STRATEGY_MAP = {
    "passthrough": PassthroughStrategy,
    "stall": StallDetectionStrategy,
    "confidence": ConfidenceThresholdStrategy,
}

def _build_strategy() -> RoutingStrategy:
    if not STALL_DETECTION_ENABLED:
        return PassthroughStrategy()
    cls = _STRATEGY_MAP.get(ROUTING_STRATEGY_NAME, PassthroughStrategy)
    if cls == StallDetectionStrategy:
        stall_phrases = json.loads(os.environ.get("STALL_PHRASES", '["i cannot","i don\'t know how","i\'m unable","as an ai"]'))
        return StallDetectionStrategy(min_tokens=STALL_MIN_TOKENS, stall_phrases=stall_phrases)
    if cls == ConfidenceThresholdStrategy:
        threshold = float(os.environ.get("LOCAL_CONFIDENCE_THRESHOLD", "0.8"))
        return ConfidenceThresholdStrategy(threshold=threshold)
    return PassthroughStrategy()

routing_strategy = _build_strategy()

REDIS_URL_PROXY = os.environ.get("REDIS_URL", "redis://localhost:6379")


def _log_escalation(problem_uuid: str | None) -> None:
    """Increment Redis escalation counters (fire-and-forget, never raises)."""
    try:
        r = _redis_sync.from_url(REDIS_URL_PROXY, decode_responses=True, socket_timeout=1)
        r.incr("oak:telemetry:escalations")
        if problem_uuid:
            r.hincrby(f"oak:telemetry:problem:{problem_uuid}", "escalations", 1)
        r.close()
    except Exception:
        pass  # telemetry is non-blocking; proxy must not fail on Redis down


async def proxy(request: Request, path: str) -> Response:
    """
    Core proxy function. NEVER modify this function — routing decisions
    are delegated entirely to routing_strategy.should_escalate().
    """
    # Log total call count
    try:
        r = _redis_sync.from_url(REDIS_URL_PROXY, decode_responses=True, socket_timeout=1)
        r.incr("oak:telemetry:total_calls")
        r.close()
    except Exception:
        pass  # telemetry is non-blocking; proxy must not fail on Redis down

    body = await request.body()
    headers = dict(request.headers)
    headers.pop("host", None)
    headers["Authorization"] = "Bearer ollama"

    # Forward to Ollama
    async with httpx.AsyncClient(timeout=120) as client:
        ollama_resp = await client.request(
            method=request.method,
            url=f"{OLLAMA_BASE_URL}/v1/{path}",
            content=body,
            headers=headers,
        )

    # Check if escalation is needed
    try:
        local_response = ollama_resp.json()
    except Exception:
        local_response = {}

    should_escalate = await routing_strategy.should_escalate(
        json.loads(body) if body else {}, local_response
    )

    if should_escalate and ANTHROPIC_API_KEY_REAL:
        escalation_headers = dict(request.headers)
        escalation_headers.pop("host", None)
        escalation_headers["x-api-key"] = ANTHROPIC_API_KEY_REAL
        escalation_headers.pop("authorization", None)
        async with httpx.AsyncClient(timeout=180) as client:
            claude_resp = await client.request(
                method=request.method,
                url=f"{ANTHROPIC_BASE_URL}/v1/{path}",
                content=body,
                headers=escalation_headers,
            )
        problem_uuid = headers.get("x-oak-problem-uuid")
        _log_escalation(problem_uuid)
        return Response(
            content=claude_resp.content,
            status_code=claude_resp.status_code,
            headers=dict(claude_resp.headers),
        )

    return Response(
        content=ollama_resp.content,
        status_code=ollama_resp.status_code,
        headers=dict(ollama_resp.headers),
    )


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def catch_all(request: Request, path: str):
    return await proxy(request, path)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "routing_strategy": ROUTING_STRATEGY_NAME,
        "stall_detection_enabled": STALL_DETECTION_ENABLED,
        "ollama_url": OLLAMA_BASE_URL,
        "escalation_available": bool(ANTHROPIC_API_KEY_REAL),
    }
