#!/bin/bash
# OAK PostToolUse Hook — thin telemetry relay (PRD anti-pattern AP-4: hooks are thin relays)
# Receives JSON on stdin: {"tool_name": "...", "tool_input": {...}, "tool_response": {...}}
# NEVER blocks (always exits 0). Never contains business logic.
set -euo pipefail

PAYLOAD=$(cat)
START_MS=${OAK_TOOL_START_MS:-0}
NOW_MS=$(date +%s%3N 2>/dev/null || echo "0")
DURATION_MS=$(( NOW_MS - START_MS ))

OAK_API="${OAK_API_URL:-http://oak-api:8000}"
AGENT_ID="${OAK_AGENT_ID:-unknown}"
PROBLEM_UUID="${OAK_PROBLEM_UUID:-}"

TELEMETRY=$(python3 - <<'PYEOF' <<< "$PAYLOAD"
import sys, json, os

payload = json.load(sys.stdin)
tool_name = payload.get("tool_name", "unknown")
tool_input = payload.get("tool_input")
tool_response = payload.get("tool_response")

event = {
    "agent_id": os.environ.get("OAK_AGENT_ID", "unknown"),
    "event_type": "tool_called",
    "tool_name": tool_name,
    "tool_input": tool_input if isinstance(tool_input, dict) else None,
    "tool_response": tool_response if isinstance(tool_response, dict) else None,
    "duration_ms": int(os.environ.get("DURATION_MS", "0")),
    "escalated": False,
}

puuid = os.environ.get("OAK_PROBLEM_UUID", "")
if puuid and puuid != "00000000-0000-0000-0000-000000000000":
    event["problem_id"] = puuid

print(json.dumps(event))
PYEOF
) 2>/dev/null || true

if [ -n "$TELEMETRY" ]; then
    # POST to /api/telemetry — fire-and-forget, never block
    DURATION_MS=$DURATION_MS curl -s -m 2 -X POST \
        "$OAK_API/api/telemetry" \
        -H "Content-Type: application/json" \
        -d "$TELEMETRY" \
        > /dev/null 2>&1 || true
fi

exit 0
