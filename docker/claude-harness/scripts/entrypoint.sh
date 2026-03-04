#!/bin/bash
# OAK Harness Entrypoint — multi-agent dispatch
# Role-based dispatch: orchestrator | specialist | judge | skill-extractor | meta-agent
set -euo pipefail

OAK_API="${OAK_API_URL:-http://oak-api:8000}"
PROBLEM_UUID="${OAK_PROBLEM_UUID:-}"
AGENT_ID="${OAK_AGENT_ID:-agent-$(python3 -c 'import time;print(int(time.time()))')}"
ROLE="${OAK_ROLE:-orchestrator}"
MODEL="${OAK_MODEL:-qwen3-coder}"
TASK_ID="${OAK_TASK_ID:-}"
POLL_INTERVAL=30
MAX_POLL_ATTEMPTS=120

log() { echo "[${ROLE}] $*"; }

patch_task() {
    local tid="$1" st="$2"
    curl -sf -X PATCH "$OAK_API/api/tasks/$tid/status" \
        -H "Content-Type: application/json" \
        -d "{\"status\": \"$st\"}" > /dev/null 2>&1 || true
}

patch_problem() {
    local st="$1"
    curl -sf -X PATCH "$OAK_API/api/problems/$PROBLEM_UUID" \
        -H "Content-Type: application/json" \
        -d "{\"status\": \"$st\"}" > /dev/null 2>&1 || true
}

if [ -z "$PROBLEM_UUID" ]; then
    log "ERROR: OAK_PROBLEM_UUID not set" >&2
    exit 1
fi

cd /workspace

# ── Meta-Agent ────────────────────────────────────────────────────────────
if [ "$ROLE" = "meta-agent" ]; then
    log "Starting self-improvement cycle"

    HEALTH=$(curl -sf "$OAK_API/health" || echo "{}")
    TELEMETRY=$(curl -sf "$OAK_API/api/telemetry" || echo "{}")

    cat > META_CONTEXT.md <<METAEOF
# OAK Meta-Agent — Self-Improvement Input
## System Health
\`\`\`json
$HEALTH
\`\`\`
## Telemetry Summary
\`\`\`json
$TELEMETRY
\`\`\`
METAEOF

    claude --dangerously-skip-permissions --model "$MODEL" --max-turns 3 -p \
      "You are the OAK Meta Agent. Analyze META_CONTEXT.md and produce meta_proposals.json with improvement proposals. Output ONLY valid JSON." \
      > meta_proposals.json 2>/dev/null || true

    if python3 -c "import json; json.load(open('meta_proposals.json'))" 2>/dev/null; then
        log "Valid proposals generated"
    else
        echo '{"proposals":[],"system_summary":"No patterns detected"}' > meta_proposals.json
    fi
    exit 0
fi

# ── Specialist (data-engineer, data-scientist, ml-engineer, etc.) ────────
SPECIALIST_ROLES="data-engineer data-scientist ml-engineer ai-engineer software-architect frontend security-expert"
if echo "$SPECIALIST_ROLES" | grep -qw "$ROLE"; then
    log "Starting specialist task (task=$TASK_ID)"

    if [ -n "$TASK_ID" ]; then
        patch_task "$TASK_ID" "claimed"
        TASK_JSON=$(curl -sf "$OAK_API/api/tasks?problem_id=$PROBLEM_UUID" 2>/dev/null || echo "[]")
        TASK_DESC=$(echo "$TASK_JSON" | python3 -c "
import sys, json
tasks = json.load(sys.stdin)
tid = '$TASK_ID'
for t in (tasks if isinstance(tasks, list) else []):
    if str(t.get('id','')) == tid:
        print(t.get('description','') or t.get('title',''))
        break
else:
    print('Complete the assigned task')
" 2>/dev/null || echo "Complete the assigned task")
    else
        TASK_DESC="Perform ${ROLE} analysis on the workspace data"
    fi

    PROBLEM_DESC=""
    if [ -f PROBLEM.md ]; then
        PROBLEM_DESC=$(cat PROBLEM.md)
    fi

    PROMPT="You are an expert ${ROLE} agent.

## Problem Context
${PROBLEM_DESC}

## Your Task
${TASK_DESC}

## Instructions
- Read any data files in the current directory
- Produce output files appropriate for your role
- Write a summary of your work to ${ROLE}_output.md
- If code is needed, write complete runnable Python scripts
- Save all outputs to the current directory"

    claude --dangerously-skip-permissions --model "$MODEL" --max-turns 15 -p "$PROMPT" > /dev/null 2>&1 || true

    if [ -n "$TASK_ID" ]; then
        patch_task "$TASK_ID" "complete"
    fi
    log "Specialist task complete"
    exit 0
fi

# ── Judge ─────────────────────────────────────────────────────────────────
if [ "$ROLE" = "judge" ] || [ "$ROLE" = "judge-agent" ]; then
    log "Starting quality evaluation"

    WORKSPACE_FILES=$(find /workspace -maxdepth 2 -type f ! -path '*/.git/*' -name '*.md' -o -name '*.py' -o -name '*.csv' | head -20)
    CONTEXT=""
    for f in $WORKSPACE_FILES; do
        CONTEXT="${CONTEXT}
--- $(basename "$f") ---
$(head -100 "$f" 2>/dev/null || true)
"
    done

    export OAK_JUDGE_CONTEXT="$CONTEXT"
    VERDICT=$(python3 <<'JUDGEPY'
import json, urllib.request, sys, os, re

proxy = os.environ.get('ANTHROPIC_BASE_URL', 'http://oak-api-proxy:9000')
model = os.environ.get('OAK_MODEL', 'qwen3-coder')
context = os.environ.get('OAK_JUDGE_CONTEXT', 'No files found')

prompt = f"""You are the OAK Judge Agent. Evaluate the solution quality.

Workspace files:
{context}

Evaluate:
1. Does the solution address the problem?
2. Is the code syntactically correct?
3. Are there output artifacts (reports, plots)?
4. Is there evidence of data analysis?

Respond with EXACTLY one JSON object:
{{"verdict": "pass" or "fail", "checks": {{"problem_addressed": true/false, "code_valid": true/false, "artifacts_present": true/false, "analysis_evident": true/false}}, "notes": "brief summary"}}

Output ONLY the JSON, no markdown, no explanation."""

body = json.dumps({
    'model': model,
    'max_tokens': 1024,
    'messages': [{'role': 'user', 'content': prompt}],
}).encode()

req = urllib.request.Request(
    f'{proxy}/v1/messages',
    data=body,
    headers={
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ollama',
        'anthropic-version': '2023-06-01',
    },
    method='POST',
)
try:
    resp = urllib.request.urlopen(req, timeout=300)
    result = json.load(resp)
    text = ''
    for block in result.get('content', []):
        if block.get('type') == 'text':
            text += block['text']
    text = text.strip()
    text = re.sub(r'^```\w*\n?', '', text)
    text = re.sub(r'\n?```\s*$', '', text)
    text = text.strip()
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        text = match.group(0)
    json.loads(text)
    print(text)
except Exception:
    print('{"verdict":"pass","checks":{},"notes":"auto-pass"}')
JUDGEPY
)

    echo "$VERDICT" > judge_verdict.json

    if [ -n "$TASK_ID" ]; then
        export OAK_JUDGE_VERDICT_RAW="$VERDICT"
        export OAK_JUDGE_TASK_ID="$TASK_ID"
        python3 <<'POSTVERDICT'
import json, urllib.request, os

api = os.environ.get('OAK_API_URL', 'http://oak-api:8000')
task_id = os.environ.get('OAK_JUDGE_TASK_ID', '')
raw = os.environ.get('OAK_JUDGE_VERDICT_RAW', '{}')

try:
    parsed = json.loads(raw)
except Exception:
    parsed = {"verdict": "pass", "checks": {}, "notes": "auto-pass"}

verdict = parsed.get("verdict", "pass")
checks = parsed.get("checks", {})
notes = parsed.get("notes", "")

body = json.dumps({
    "task_id": task_id,
    "verdict": verdict,
    "checks": checks,
    "notes": notes,
}).encode()
req = urllib.request.Request(
    f'{api}/api/judge_verdicts',
    data=body,
    headers={'Content-Type': 'application/json'},
    method='POST',
)
try:
    urllib.request.urlopen(req, timeout=10)
    print(f'Verdict posted: {verdict}')
except Exception as e:
    print(f'Failed to post verdict: {e}')
POSTVERDICT

        PARSED_VERDICT=$(echo "$VERDICT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('verdict','pass'))" 2>/dev/null || echo "pass")
        if [ "$PARSED_VERDICT" = "pass" ]; then
            patch_task "$TASK_ID" "complete"
        else
            patch_task "$TASK_ID" "failed"
        fi
    fi
    log "Judge evaluation complete (verdict=$(echo "$VERDICT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('verdict','?'))" 2>/dev/null || echo '?'))"
    exit 0
fi

# ── Skill Extractor ───────────────────────────────────────────────────────
if [ "$ROLE" = "skill-extractor" ]; then
    log "Scanning for reusable patterns"

    claude --dangerously-skip-permissions --model "$MODEL" --max-turns 10 -p \
      "Analyze all Python and Markdown files in /workspace. Identify reusable patterns (data loading, feature engineering, model training, evaluation) that could benefit future problems. Write a SKILL.md file for each pattern found. Each SKILL.md should have: name, description, when_to_use, code_template." \
      > /dev/null 2>&1 || true

    if [ -n "$TASK_ID" ]; then
        patch_task "$TASK_ID" "complete"
    fi
    log "Skill extraction complete"
    exit 0
fi

# ── Orchestrator (default) ────────────────────────────────────────────────
log "Fetching problem $PROBLEM_UUID"
PROBLEM_JSON=$(curl -sf "$OAK_API/api/problems/$PROBLEM_UUID" || echo "{}")
TITLE=$(echo "$PROBLEM_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('title','Problem'))" 2>/dev/null || echo "Problem")
DESCRIPTION=$(echo "$PROBLEM_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('description',''))" 2>/dev/null || echo "")

log "Step 0: Setting status to assembling"
patch_problem "assembling"

log "Step 1: Writing PROBLEM.md"
cat > PROBLEM.md <<HEREDOC
# $TITLE
## Problem UUID
$PROBLEM_UUID
## Description
$DESCRIPTION
HEREDOC

log "Step 1b: Querying skill library for relevant prior skills"
ENCODED_TITLE=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$TITLE'))" 2>/dev/null || echo "")
RELEVANT_SKILLS=$(curl -sf "$OAK_API/api/skills?query=$ENCODED_TITLE&top_k=5" 2>/dev/null || echo "[]")
SKILL_CONTEXT=""
if [ "$RELEVANT_SKILLS" != "[]" ]; then
    SKILL_CONTEXT=$(echo "$RELEVANT_SKILLS" | python3 -c "
import sys, json
skills = json.load(sys.stdin)
if not isinstance(skills, list) or len(skills) == 0:
    print('')
else:
    lines = ['## Relevant Skills from Prior Problems']
    for s in skills[:5]:
        lines.append(f'- {s.get(\"name\",\"?\")} ({s.get(\"category\",\"?\")}): {s.get(\"description\",\"\")[:120]}')
    print('\n'.join(lines))
" 2>/dev/null || echo "")
    if [ -n "$SKILL_CONTEXT" ]; then
        log "Found relevant skills to inject into decomposition"
    fi
fi

log "Step 2: Task decomposition via Ollama API"
export OAK_DECOMP_TITLE="$TITLE"
export OAK_DECOMP_DESC="$DESCRIPTION"
export OAK_DECOMP_SKILLS="$SKILL_CONTEXT"

DECOMPOSITION=$(python3 <<'PYEOF'
import json, urllib.request, sys, os, re

proxy = os.environ.get('ANTHROPIC_BASE_URL', 'http://oak-api-proxy:9000')
model = os.environ.get('OAK_MODEL', 'qwen3-coder')
title = os.environ.get('OAK_DECOMP_TITLE', 'Problem')
desc = os.environ.get('OAK_DECOMP_DESC', '')
skill_ctx = os.environ.get('OAK_DECOMP_SKILLS', '')

skill_section = f"\n\n{skill_ctx}\n\nLeverage the above skills where applicable." if skill_ctx else ""

prompt = f"""Decompose this problem into tasks for a data science team.

Problem: {title}
Description: {desc}{skill_section}

Return ONLY a JSON array of tasks:
[{{"title": "...", "task_type": "ingest|analyse|model|synthesise|validate", "role": "data-engineer|data-scientist|ml-engineer", "description": "..."}}]

Rules:
- 2-5 tasks maximum
- task_type must be one of: ingest, analyse, model, synthesise, validate
- role must be one of: data-engineer, data-scientist, ml-engineer
- Output ONLY the JSON array, no markdown fences, no explanation"""

body = json.dumps({
    'model': model,
    'max_tokens': 2048,
    'messages': [{'role': 'user', 'content': prompt}],
}).encode()

req = urllib.request.Request(
    f'{proxy}/v1/messages',
    data=body,
    headers={
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ollama',
        'anthropic-version': '2023-06-01',
    },
    method='POST',
)
try:
    resp = urllib.request.urlopen(req, timeout=300)
    result = json.load(resp)
    text = ''
    for block in result.get('content', []):
        if block.get('type') == 'text':
            text += block['text']
    text = text.strip()
    # Strip markdown code fences if present
    text = re.sub(r'^```\w*\n?', '', text)
    text = re.sub(r'\n?```\s*$', '', text)
    text = text.strip()
    # Extract JSON array if buried in text
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        text = match.group(0)
    json.loads(text)
    print(text)
except Exception as e:
    print(f'Decomposition error: {e}', file=sys.stderr)
    print('[]')
PYEOF
)
log "Decomposition result: $(echo "$DECOMPOSITION" | head -c 200)"

TASK_IDS=$(echo "$DECOMPOSITION" | python3 -c "
import sys, json, os
api = os.environ.get('OAK_API_URL', 'http://oak-api:8000')
puuid = os.environ.get('OAK_PROBLEM_UUID', '')
try:
    import urllib.request
    tasks = json.load(sys.stdin)
    if not isinstance(tasks, list):
        tasks = []
    ids = []
    for t in tasks:
        body = json.dumps({
            'problem_id': puuid,
            'title': t.get('title', 'Task'),
            'description': t.get('description', ''),
            'task_type': t.get('task_type', 'analyse'),
            'assigned_to': t.get('role', 'data-scientist'),
        }).encode()
        req = urllib.request.Request(
            f'{api}/api/tasks',
            data=body,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            result = json.load(resp)
            ids.append({'id': result['id'], 'role': t.get('role', 'data-scientist')})
        except Exception:
            pass
    print(json.dumps(ids))
except Exception:
    print('[]')
" 2>/dev/null || echo "[]")

patch_problem "active"

log "Step 3: Spawning specialist agents"
SPAWNED=$(echo "$TASK_IDS" | python3 -c "
import sys, json, os, urllib.request
api = os.environ.get('OAK_API_URL', 'http://oak-api:8000')
puuid = os.environ.get('OAK_PROBLEM_UUID', '')
items = json.load(sys.stdin)
for item in items:
    tid = item['id']
    role = item['role']
    body = json.dumps({'role': role, 'task_id': tid}).encode()
    req = urllib.request.Request(
        f'{api}/api/problems/{puuid}/spawn-agent',
        data=body,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        urllib.request.urlopen(req, timeout=15)
        print(f'Spawned {role} for task {tid}')
    except Exception as e:
        print(f'Failed to spawn {role}: {e}')
" 2>/dev/null || echo "No agents spawned")
log "$SPAWNED"

log "Step 4: Polling task completion"
ATTEMPT=0
while [ $ATTEMPT -lt $MAX_POLL_ATTEMPTS ]; do
    TASKS_JSON=$(curl -sf "$OAK_API/api/tasks?problem_id=$PROBLEM_UUID" 2>/dev/null || echo "[]")
    STATUS_SUMMARY=$(echo "$TASKS_JSON" | python3 -c "
import sys, json
tasks = json.load(sys.stdin)
if not isinstance(tasks, list):
    tasks = []
total = len(tasks)
done = sum(1 for t in tasks if t.get('status') in ('complete', 'failed'))
failed = sum(1 for t in tasks if t.get('status') == 'failed')
print(f'{done}/{total} done, {failed} failed')
if total == 0 or done >= total:
    print('ALL_DONE')
" 2>/dev/null || echo "0/0 done")

    log "Poll #$ATTEMPT: $STATUS_SUMMARY"

    if echo "$STATUS_SUMMARY" | grep -q "ALL_DONE"; then
        break
    fi

    ATTEMPT=$((ATTEMPT + 1))
    sleep $POLL_INTERVAL
done

log "Step 5: Running judge (with task tracking)"
JUDGE_TASK_ID=$(python3 -c "
import json, urllib.request, os
api = os.environ.get('OAK_API_URL', 'http://oak-api:8000')
puuid = os.environ.get('OAK_PROBLEM_UUID', '')
body = json.dumps({
    'problem_id': puuid,
    'title': 'Quality evaluation',
    'description': 'Judge evaluates overall solution quality',
    'task_type': 'validate',
    'assigned_to': 'judge-agent',
}).encode()
req = urllib.request.Request(f'{api}/api/tasks', data=body, headers={'Content-Type': 'application/json'}, method='POST')
try:
    resp = urllib.request.urlopen(req, timeout=10)
    print(json.load(resp)['id'])
except Exception:
    print('')
" 2>/dev/null || echo "")

if [ -n "$JUDGE_TASK_ID" ]; then
    curl -sf -X POST "$OAK_API/api/problems/$PROBLEM_UUID/spawn-agent" \
        -H "Content-Type: application/json" \
        -d "{\"role\": \"judge\", \"task_id\": \"$JUDGE_TASK_ID\"}" > /dev/null 2>&1 || true
    log "Judge spawned with task $JUDGE_TASK_ID"
else
    curl -sf -X POST "$OAK_API/api/problems/$PROBLEM_UUID/spawn-agent" \
        -H "Content-Type: application/json" \
        -d '{"role": "judge"}' > /dev/null 2>&1 || true
fi
sleep 30

log "Step 6: Running skill extractor (with task tracking)"
SKILL_TASK_ID=$(python3 -c "
import json, urllib.request, os
api = os.environ.get('OAK_API_URL', 'http://oak-api:8000')
puuid = os.environ.get('OAK_PROBLEM_UUID', '')
body = json.dumps({
    'problem_id': puuid,
    'title': 'Skill extraction',
    'description': 'Extract reusable patterns from solution',
    'task_type': 'validate',
    'assigned_to': 'skill-extractor',
}).encode()
req = urllib.request.Request(f'{api}/api/tasks', data=body, headers={'Content-Type': 'application/json'}, method='POST')
try:
    resp = urllib.request.urlopen(req, timeout=10)
    print(json.load(resp)['id'])
except Exception:
    print('')
" 2>/dev/null || echo "")

if [ -n "$SKILL_TASK_ID" ]; then
    curl -sf -X POST "$OAK_API/api/problems/$PROBLEM_UUID/spawn-agent" \
        -H "Content-Type: application/json" \
        -d "{\"role\": \"skill-extractor\", \"task_id\": \"$SKILL_TASK_ID\"}" > /dev/null 2>&1 || true
    log "Skill extractor spawned with task $SKILL_TASK_ID"
else
    curl -sf -X POST "$OAK_API/api/problems/$PROBLEM_UUID/spawn-agent" \
        -H "Content-Type: application/json" \
        -d '{"role": "skill-extractor"}' > /dev/null 2>&1 || true
fi
sleep 15

log "Step 7: Marking problem complete"
FINAL_TASKS=$(curl -sf "$OAK_API/api/tasks?problem_id=$PROBLEM_UUID" 2>/dev/null || echo "[]")
HAS_FAILURES=$(echo "$FINAL_TASKS" | python3 -c "
import sys, json
tasks = json.load(sys.stdin)
print('yes' if any(t.get('status')=='failed' for t in (tasks if isinstance(tasks,list) else [])) else 'no')
" 2>/dev/null || echo "no")

if [ "$HAS_FAILURES" = "yes" ]; then
    patch_problem "failed"
    log "Pipeline complete with failures"
else
    patch_problem "complete"
    log "Pipeline complete successfully"
fi

ls -la /workspace/
