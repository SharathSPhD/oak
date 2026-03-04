#!/bin/bash
# Create a new OAK problem workspace and launch orchestrator
# Usage: bash scripts/new-problem.sh "Problem Title" "Description"
#    or: bash scripts/new-problem.sh [uuid]  (legacy mode)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OAK_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OAK_API="${OAK_API_URL:-http://localhost:8000}"

OAK_PROJECT="$(basename "${OAK_ROOT}")"
OAK_NETWORK="${OAK_PROJECT}_oak-net"

if [[ "${1:-}" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]; then
    PROBLEM_UUID="$1"
    echo "[new-problem] Legacy mode: using existing UUID $PROBLEM_UUID"
else
    TITLE="${1:-Untitled Problem}"
    DESCRIPTION="${2:-}"
    echo "[new-problem] Creating problem via API: $TITLE"
    RESP=$(curl -sf -X POST "$OAK_API/api/problems" \
        -H "Content-Type: application/json" \
        -d "{\"title\": \"$TITLE\", \"description\": \"$DESCRIPTION\"}" 2>&1) || {
        echo "[error] Failed to create problem via API. Is the stack running?"
        exit 1
    }
    PROBLEM_UUID=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)
    if [ -z "$PROBLEM_UUID" ]; then
        echo "[error] Could not parse UUID from API response: $RESP"
        exit 1
    fi
    echo "[new-problem] Created problem: $PROBLEM_UUID"
fi

BRANCH="oak/problem-${PROBLEM_UUID}"
WORKTREE_PATH="${HOME}/oak-workspaces/problem-${PROBLEM_UUID}"

echo "[new-problem] UUID    : $PROBLEM_UUID"
echo "[new-problem] Network : $OAK_NETWORK"

if [ -d "$WORKTREE_PATH" ]; then
    echo "[new-problem] Worktree already exists at $WORKTREE_PATH"
else
    git -C "${OAK_ROOT}" worktree add -b "$BRANCH" "$WORKTREE_PATH" main 2>/dev/null || \
    git -C "${OAK_ROOT}" worktree add "$WORKTREE_PATH" "$BRANCH" 2>/dev/null || {
        echo "[warn] Worktree creation failed; using mkdir"
        mkdir -p "$WORKTREE_PATH"
    }
fi

docker run -d \
    --name "oak-harness-${PROBLEM_UUID}" \
    --network "${OAK_NETWORK}" \
    -e ANTHROPIC_BASE_URL=http://oak-api-proxy:9000 \
    -e ANTHROPIC_AUTH_TOKEN=ollama \
    -e ANTHROPIC_API_KEY="ollama" \
    -e OAK_PROBLEM_UUID="$PROBLEM_UUID" \
    -e OAK_API_URL=http://oak-api:8000 \
    -e REDIS_URL=redis://oak-redis:6379 \
    -e DATABASE_URL=postgresql://oak:oak@oak-postgres:5432/oak \
    -v "${WORKTREE_PATH}:/workspace" \
    -v "${OAK_ROOT}/scripts/deny-patterns.txt:/workspace/scripts/deny-patterns.txt:ro" \
    oak/harness:latest

echo "[new-problem] Workspace : $WORKTREE_PATH"
echo "[new-problem] Branch    : $BRANCH"
echo "[new-problem] Container : oak-harness-${PROBLEM_UUID}"
echo "[new-problem] Logs      : docker logs -f oak-harness-${PROBLEM_UUID}"
