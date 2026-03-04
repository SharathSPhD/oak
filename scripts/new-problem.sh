#!/bin/bash
# Create a new OAK problem workspace and launch orchestrator
# Usage: bash scripts/new-problem.sh [uuid]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OAK_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PROBLEM_UUID="${1:-$(python3 -c 'import uuid; print(uuid.uuid4())')}"
BRANCH="oak/problem-${PROBLEM_UUID}"
WORKTREE_PATH="${HOME}/oak-workspaces/problem-${PROBLEM_UUID}"

# Resolve the docker compose network name (project name prefix + oak-net)
OAK_PROJECT="$(basename "${OAK_ROOT}")"
OAK_NETWORK="${OAK_PROJECT}_oak-net"

echo "[new-problem] UUID: $PROBLEM_UUID"
echo "[new-problem] Network: $OAK_NETWORK"

# Create branch + worktree
git -C "${OAK_ROOT}" worktree add -b "$BRANCH" "$WORKTREE_PATH" main

# Launch orchestrator container
docker run -d \
    --name "oak-harness-${PROBLEM_UUID}" \
    --network "${OAK_NETWORK}" \
    -e ANTHROPIC_BASE_URL=http://oak-api-proxy:9000 \
    -e ANTHROPIC_AUTH_TOKEN=ollama \
    -e ANTHROPIC_API_KEY="" \
    -e OAK_PROBLEM_UUID="$PROBLEM_UUID" \
    -e OAK_API_URL=http://oak-api:8000 \
    -v "${WORKTREE_PATH}:/workspace" \
    oak/harness:latest

echo "[new-problem] Workspace : $WORKTREE_PATH"
echo "[new-problem] Branch    : $BRANCH"
echo "[new-problem] Container : oak-harness-${PROBLEM_UUID}"
echo "[new-problem] Logs      : docker logs -f oak-harness-${PROBLEM_UUID}"
