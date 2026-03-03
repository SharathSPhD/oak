#!/bin/bash
# docker/claude-harness/scripts/tool-proxy.sh
# Layer 1 deny-list interceptor. Runs INSIDE the harness container.
# Receives: OAK_TOOL_CMD, OAK_AGENT_ID, OAK_PROBLEM_UUID via environment
# Exit 2 = block. Exit 0 = allow and log to Redis.
set -euo pipefail

CMD="${OAK_TOOL_CMD:-}"
AGENT="${OAK_AGENT_ID:-unknown}"
PROBLEM="${OAK_PROBLEM_UUID:-unknown}"
REDIS_URL="${REDIS_URL:-redis://oak-redis:6379}"

# Shared deny patterns — same file used by pre-tool-use.sh (Layer 2)
DENY_FILE="/workspace/scripts/deny-patterns.txt"

if [ -f "$DENY_FILE" ]; then
    while IFS= read -r pattern; do
        [ -z "$pattern" ] && continue
        [[ "${pattern:0:1}" == "#" ]] && continue
        [[ "$pattern" == OAK:* ]] && continue  # OAK: rules are Layer 2
        if echo "$CMD" | grep -qiE "$pattern"; then
            echo "[OAK-PROXY] BLOCKED by deny list: $pattern" >&2
            # Log to Redis for telemetry (best-effort)
            redis-cli -u "$REDIS_URL" LPUSH "oak:blocked:${AGENT}" \
                "{\"cmd\":\"${CMD:0:200}\",\"pattern\":\"$pattern\",\"ts\":\"$(date -u +%s)\"}" \
                >/dev/null 2>&1 || true
            exit 2
        fi
    done < "$DENY_FILE"
fi

# Log approved command to Redis session history (best-effort)
redis-cli -u "$REDIS_URL" LPUSH "oak:session:${AGENT}:cmd_history" \
    "{\"cmd\":\"${CMD:0:200}\",\"ts\":\"$(date -u +%s)\"}" >/dev/null 2>&1 || true
redis-cli -u "$REDIS_URL" LTRIM "oak:session:${AGENT}:cmd_history" 0 49 >/dev/null 2>&1 || true

exit 0
