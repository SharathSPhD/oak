#!/bin/bash
# OAK Harness Entrypoint
# Fetches problem from API and injects as initial task prompt to Claude Code
set -euo pipefail

OAK_API="${OAK_API_URL:-http://oak-api:8000}"
PROBLEM_UUID="${OAK_PROBLEM_UUID:-}"
AGENT_ID="${OAK_AGENT_ID:-orchestrator-$(date +%s)}"
ROLE="${OAK_ROLE:-orchestrator}"

if [ -z "$PROBLEM_UUID" ]; then
    echo "[entrypoint] ERROR: OAK_PROBLEM_UUID not set" >&2
    exit 1
fi

echo "[entrypoint] Fetching problem $PROBLEM_UUID from $OAK_API..."
PROBLEM_JSON=$(curl -sf "$OAK_API/api/problems/$PROBLEM_UUID" || echo "{}")
TITLE=$(echo "$PROBLEM_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('title','Unknown Problem'))" 2>/dev/null || echo "Problem $PROBLEM_UUID")
DESCRIPTION=$(echo "$PROBLEM_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('description',''))" 2>/dev/null || echo "")

INITIAL_PROMPT="You are the OAK Orchestrator agent.

Problem UUID: $PROBLEM_UUID
Title: $TITLE
Description: $DESCRIPTION

Your task: Follow the OAK agent lifecycle (RESTORE → ORIENT → SKILL_QUERY → EXECUTE → VALIDATE → REPORT → CLOSE → SAVE) as defined in your agent definition. Start by writing PROBLEM.md to the workspace, then create and assign tasks to specialist agents.

Begin now."

echo "[entrypoint] Starting Claude Code orchestrator for problem $PROBLEM_UUID"
MODEL="${OAK_MODEL:-claude-sonnet-4-6}"
exec claude --dangerously-skip-permissions --model "$MODEL" -p "$INITIAL_PROMPT"
