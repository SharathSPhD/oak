# OAK Progress Log

## Phase 0 — Walking Skeleton

### Status: CODE COMPLETE — awaiting Docker stack verification

| Exit Criterion | Status | Notes |
|---|---|---|
| `docker compose up` — 4 services healthy | ⏳ Stack not started | Compose files exist; run `docker compose -f docker/docker-compose.dgx.yml up -d` |
| `psql` shows all 8 schema tables | ⏳ Needs running stack | `api/db/schema.sql` DDL complete; init container mounts it |
| `POST /api/problems` returns 201 | ✅ Implemented | `api/routers/problems.py` + Pydantic models complete |
| CI integration test: CSV → PG table + `app.py` | ✅ Done | `tests/integration/test_phase0_pipeline.py` — 4 tests (DB mocked) |
| 57 unit+integration+contract tests passing | ✅ Done | `pytest tests/` — 57 passed, 3 skipped (Redis) |
| All compose files exist | ✅ Done | `docker/docker-compose.{dgx,mini,cloud,base}.yml` |
| FastAPI app with all 5 routers + WebSocket | ✅ Done | `api/main.py` + `api/routers/` |
| DB schema DDL | ✅ Done | `api/db/schema.sql` — 8 tables + pgvector indexes |
| Memory interfaces (Repository pattern) | ✅ Done | `memory/interfaces.py` |
| ChainOfResponsibility validation chain | ✅ Done | `memory/validation_chain.py` — 8 tests |
| Contract tests (tool-proxy + session-state) | ✅ Done | `tests/contract/` — 11 pass, 3 skipped (Redis) |
| Agent definitions | ✅ Done | `.claude/agents/*.md` — 8 agents |
| Hooks (pre/post/task-gate/teammate-idle) | ✅ Done | `.claude/hooks/*.sh` |
| Seed skills (probationary) | ✅ Done | 2 skills in `~/oak-workspaces/skills/probationary/` |
| `__pattern__` CI enforcement | ✅ Done | `tests/conftest.py` + `.github/workflows/ci.yml` |
| Deny-pattern ERE+Python-re compatibility | ✅ Done | Consolidated to `(sh\|bash\|python)` grouping |

### Integration Branch
All Phase 0 feature work is consolidated on `feat/phase0-integration`. Pending merge to `main` via PR.

---

## Phase 1 — Hardened Harness + Single Agent

### Status: CODE COMPLETE — awaiting Docker stack + Redis verification

| Exit Criterion | Status | Notes |
|---|---|---|
| All harness/proxy unit tests pass in CI | ✅ Done | 74 tests pass, 3 skipped (Redis) |
| Tool proxy blocks all canonical deny patterns | ✅ Done | `tests/contract/test_tool_proxy.py` — 11 pass |
| Redis session state survives container restart | ⏳ Needs Redis | `test_session_state.py` — 3 skipped; runs when Redis up |
| `GET /api/agents/status` shows running agents | ✅ Done | `api/services/agent_registry.py` — Redis-backed |
| DGXAgentFactory spawns harness container | ✅ Done | `api/factories/agent_factory.py` — subprocess docker run |
| Proxy routing strategies unit tested | ✅ Done | `tests/unit/test_proxy_strategies.py` — 8 pass |
| SessionStateSubscriber updates Redis on events | ✅ Done | `api/events/bus.py` — lifecycle events wired |

### Integration Branch
`feat/phase1-integration` → pending merge to `main` via PR.
PR: https://github.com/SharathSPhD/oak/pull/new/feat/phase1-integration

### Remaining Gate
Start the Docker stack + Redis to unblock 3 session-state contract tests:
```bash
docker compose -f docker/docker-compose.dgx.yml up -d oak-postgres oak-redis oak-ollama oak-api
pytest tests/contract/ -v  # all 14 should pass
```

---

## Phase 2 — Agent Teams + Task List + Judge Gate

### Status: CODE COMPLETE — awaiting Docker stack + full E2E run

| Exit Criterion | Status | Notes |
|---|---|---|
| Judge gate: `POST /api/judge_verdicts` + `GET /api/judge_verdicts/{uuid}` | ✅ Done | `api/routers/judge.py` — Observer pattern + EventBus |
| Mailbox: `POST /api/mailbox` + inbox + read | ✅ Done | `api/routers/mailbox.py` + `api/services/mailbox_service.py` |
| Agent spawn: `POST /api/agents/spawn` | ✅ Done | `api/routers/agents.py` — DGXAgentFactory integration |
| Phase 2 E2E integration test | ✅ Done | `tests/integration/test_phase2_e2e.py` — 4 tests (mocked DB) |
| 85 unit + integration + contract tests passing | ✅ Done | `pytest tests/` — 85 passed, 4 skipped (Redis) |
| Full end-to-end: CSV → DE → DS → Judge PASS | ⏳ Needs Docker stack | Requires running agents + real Postgres + Redis |

### Integration Branch
`feat/phase2-integration` → merged to `main` via fast-forward.

### Remaining Gate
Start the Docker stack + Redis to unblock full E2E run:
```bash
docker compose -f docker/docker-compose.dgx.yml up -d
pytest tests/integration/ -v  # test_phase2_e2e.py needs real DB
```

---

## Phase 3 — Memory, Skill Library, and Hub

### Status: CODE COMPLETE — awaiting Docker stack + pgvector + Streamlit Cloud deploy

| Exit Criterion | Status | Notes |
|---|---|---|
| `memory/skill_repository.py` — PostgreSQL SkillRepository + pgvector | ✅ Done | `PromotionThresholdNotMet` enforced; `find_by_keywords` + `promote` |
| `memory/episodic_repository.py` — EpisodicMemoryRepository + pgvector | ✅ Done | cosine similarity (`<=>`) + `store/retrieve_similar/mark_retrieved` |
| `GET /api/skills?query=...` — semantic/keyword skill search | ✅ Done | `api/routers/skills.py` implemented |
| `POST /api/skills/{id}/promote` — promotion gate | ✅ Done | 409 if threshold not met |
| `oak-memory-mcp` — MCP tools: store_episode, retrieve_similar | ✅ Done | `oak_mcp/oak-memory-mcp/server.py` |
| `oak-skills-mcp` — MCP tools: find_skills, add_skill_use, request_promotion | ✅ Done | `oak_mcp/oak-skills-mcp/server.py` |
| WebSocket stream — Redis pub/sub `oak:stream:{uuid}` | ✅ Done | `api/ws/stream.py` — EventDriven pattern |
| Streamlit Hub — 5 pages (submit, status, gallery, skills, telemetry) | ✅ Done | `ui/app.py` + `ui/pages/02–05` |
| 99 unit + integration + contract tests passing | ✅ Done | `pytest tests/` — 99 passed, 4 skipped (Redis) |
| Skill extracted from Problem 1 reused on Problem 2 | ⏳ Needs running stack | Requires pgvector + seed skills loaded |
| Hub accessible at public Streamlit Cloud URL | ⏳ Deploy pending | `ui/app.py` ready; deploy to Streamlit Cloud from `oak/ui` branch |

### Integration Branch
`feat/phase3-integration` → merged to `main` via fast-forward.

### Remaining Gates
```bash
# Start stack + enable pgvector
docker compose -f docker/docker-compose.dgx.yml up -d

# Load seed skills into DB
psql $DATABASE_URL < scripts/seed_skills.sql

# Test skill search (requires running Postgres)
curl "http://localhost:8000/api/skills?query=csv"

# Deploy Hub to Streamlit Cloud:
# Point Streamlit Cloud to oak/ui branch, main file = ui/app.py
```

---

## Phase 4 — Mac Mini Port + Stall Detection + Telemetry

### Status: CODE COMPLETE — awaiting Docker stack + Mac Mini hardware verification

| Exit Criterion | Status | Notes |
|---|---|---|
| `docker/docker-compose.mini.yml` fully configured | ✅ Done | `oak-api` + `oak-api-proxy` services with Mac Mini profiles |
| `OAK_MODE=mini` — smaller models, lower resource caps | ✅ Done | `DEFAULT_MODEL: llama3.2:3b`, `CODER_MODEL: qwen2.5-coder:7b`, `MAX_AGENTS_PER_PROBLEM: "3"` |
| Stall detection enabled on Mini | ✅ Done | `STALL_DETECTION_ENABLED: "true"`, `ROUTING_STRATEGY: stall`, `STALL_MIN_TOKENS: "15"` |
| Proxy Redis escalation telemetry | ✅ Done | `_log_escalation()` — fire-and-forget `oak:telemetry:escalations` + per-problem counters |
| Total proxy call counter | ✅ Done | `oak:telemetry:total_calls` incremented on every proxy call |
| `GET /api/telemetry` — aggregated stats | ✅ Done | `api/routers/telemetry.py` — total events, escalation rate, events by type |
| `POST /api/telemetry` — record agent events | ✅ Done | Inserts into `agent_telemetry` table |
| `scripts/seed_skills.sql` | ✅ Done | Idempotent INSERT for `event-bus-observer` + `task-state-machine` probationary skills |
| Proxy escalation unit tests | ✅ Done | `tests/unit/test_proxy_escalation.py` — 3 pass |
| Telemetry router unit tests | ✅ Done | `tests/unit/test_telemetry.py` — 5 pass |
| 107 unit + integration + contract tests passing | ✅ Done | `pytest tests/` — 107 passed, 4 skipped (Redis) |
| Full lifecycle on `OAK_MODE=mini` | ⏳ Needs Mac Mini hardware | Stack not verified on Apple Silicon |
| Stall escalation rate < 30% | ⏳ Needs live traffic | Requires running Mini stack with real Ollama models |

### Integration Branch
`feat/phase4-integration` → merged to `main` via fast-forward.

### Remaining Gates
```bash
# Start Mini stack (on Mac Mini M4 Pro)
docker compose -f docker/docker-compose.mini.yml up -d

# Load seed skills into DB
psql $DATABASE_URL < scripts/seed_skills.sql

# Verify telemetry endpoint
curl http://localhost:8000/api/telemetry

# Monitor stall escalation rate (target < 30%)
curl http://localhost:9000/health
```

---

## Phase 5 — Concurrency Hardening + Cloud

### Status: CODE COMPLETE — awaiting cloud GPU hardware + live concurrent run verification

| Exit Criterion | Status | Notes |
|---|---|---|
| Resource caps enforced in spawn endpoint | ✅ Done | `api/routers/agents.py` — 503 on `MAX_HARNESS_CONTAINERS`, `MAX_AGENTS_PER_PROBLEM`, `MAX_CONCURRENT_PROBLEMS` |
| Atomic `promote()` with row lock | ✅ Done | `memory/skill_repository.py` — `SELECT … FOR UPDATE` inside `conn.transaction()` |
| `docker-compose.cloud.yml` — vLLM backend + api overrides | ✅ Done | `oak-api-proxy` → `oak-vllm:8000`; `oak-api` with cloud model names + raised caps |
| Resource cap unit tests | ✅ Done | `tests/unit/test_resource_caps.py` — 5 pass (all 3 cap types + happy path + existing-problem exemption) |
| Concurrent isolation unit tests | ✅ Done | `tests/unit/test_concurrent_isolation.py` — 3 pass (key scoping, FOR UPDATE, threshold guard) |
| 115 unit + integration + contract tests passing | ✅ Done | `pytest tests/` — 115 passed, 4 skipped (Redis) |
| 3 concurrent problems, zero cross-problem leakage | ⏳ Needs cloud stack | Requires live multi-GPU node + 3 parallel `new-problem.sh` runs |
| vLLM 70B with 2 concurrent requests, no OOM | ⏳ Needs cloud GPU | `docker-compose.cloud.yml` ready; needs A100/H100 node |
| Skill library race condition proof under load | ⏳ Needs load test | `FOR UPDATE` lock is in place; concurrent stress test needed |
| < 1 failure per 10 concurrent runs | ⏳ Needs live traffic | Reliability gate requires E2E runs |

### Integration Branch
`feat/phase5-isolation` → merged to `main` via fast-forward.

### Remaining Gates
```bash
# Start cloud stack (on A100/H100 node)
docker compose -f docker/docker-compose.cloud.yml up -d

# Launch 3 concurrent problems
for i in 1 2 3; do bash scripts/new-problem.sh $(uuidgen) &; done

# Verify no cross-problem data leakage
pytest tests/integration/ -k concurrent -v

# Check resource caps are observable
curl http://localhost:8000/api/agents/status
curl http://localhost:8000/api/telemetry
```

---

---

## DGX Spark Hardware Gates

### Status: COMPLETE — all gates passed on DGX Spark (NVIDIA GB10, 121 GB RAM)

| Gate | Result | Notes |
|---|---|---|
| All 6 Docker images build successfully | ✅ PASS | `oak/api-proxy`, `oak/harness`, `oak/api`, `oak/ui`, `oak/postgres` (pgvector), `oak/redis` |
| `docker compose up` — all 6 containers healthy | ✅ PASS | postgres, redis, oak-api, oak-api-proxy, oak-ollama, oak-ui all `healthy` or `Up` |
| `GET /health` on oak-api (port 8000) | ✅ PASS | `{"status":"healthy","oak_mode":"dgx","routing_strategy":"passthrough",...}` |
| `GET /health` on oak-api-proxy (port 9000) | ✅ PASS | `{"status":"healthy","routing_strategy":"passthrough","ollama_url":"http://oak-ollama:11434",...}` |
| Proxy routes `GET /v1/models` to Ollama | ✅ PASS | Returns `qwen3-coder:latest` from Ollama |
| Redis session state survives (contract tests) | ✅ PASS | `tests/contract/test_session_state.py` — 3/3 pass with live Redis |
| Tool-proxy deny-pattern blocks (contract tests) | ✅ PASS | `tests/contract/test_tool_proxy.py` — 11/11 pass |
| `GET /health` on oak-ui (port 8501) | ✅ PASS | Streamlit returns `ok` |
| Ollama model available via proxy | ✅ PASS | `qwen3-coder:latest` (18 GB) pulled and serving |
| 115 unit + integration + contract tests passing | ✅ PASS | `pytest tests/` — 115 passed, 4 skipped |
| `bootstrap.sh dgx` self-contained from any CWD | ✅ PASS | Uses `--project-directory` with script-relative OAK_ROOT |
| `restore_session()` implemented in redis_client | ✅ PASS | Scans `oak:session:{agent_id}:*` keys with TTL |
| EventBus subscribers wired (Telemetry, WS, Episodic) | ✅ PASS | All three subscribers implemented; fire-and-forget, never block producer |

### Bugs Fixed During Hardware Gates
- **Proxy 404s**: `/health` route was defined after catch-all `/{path:path}` — FastAPI matched catch-all first. Fixed by moving `/health` before catch-all.
- **Proxy double `/v1/`**: catch-all passed `v1/models` as path, proxy prepended `/v1/` → `/v1/v1/models`. Fixed: forward `/{path}` directly (Ollama supports Anthropic `/v1/messages` natively since 0.3.2).
- **UI unhealthy**: `curl` not in `python:3.11-slim`. Fixed: Python `httpx` healthcheck.
- **API missing `sqlalchemy`**: `docker/api/Dockerfile` lacked `sqlalchemy[asyncio]>=2.0`. Fixed.

### Branch
`feat/dgx-hardware-gates` → merged to `main` via fast-forward.

---

## Git Worktree Workflow

OAK uses Git worktrees to isolate concerns. Each worktree is checked out on its own branch.

### Branch → Worktree → Concern Map

| Branch | Worktree path | Concern | Who commits here |
|---|---|---|---|
| `main` | `~/oak/` | Core: API, memory, docker, scripts, tests | Feature PRs only — never direct commits |
| `oak/agents` | `~/oak-workspaces/agents/` | Agent definitions (`.claude/agents/*.md`), hooks | Meta Agent (via PR) |
| `oak/skills` | `~/oak-workspaces/skills/` | Skill library (`permanent/`, `probationary/`) | Skill Extractor Agent (automated) |
| `oak/ui` | `~/oak-workspaces/ui/` | Streamlit Hub (`app.py`, `pages/`) | Software Architect (via PR) |
| `oak/problem-{uuid}` | `~/oak-workspaces/problem-{uuid}/` | Per-problem solution code | Problem agents |

### Correct Workflow for Each Concern

**Core infrastructure change (api/, memory/, docker/, scripts/, tests/):**
```bash
cd ~/oak/                            # main worktree
git checkout -b feat/my-feature      # NEVER commit directly to main
# ... make changes ...
git add <files>
git commit -m "feat(trunk): ..."
git push origin feat/my-feature
gh pr create --base main --title "..."
```

**Agent definition update (new agent, prompt amendment):**
```bash
cd ~/oak-workspaces/agents/          # oak/agents worktree
# ... edit .claude/agents/*.md ...
git add .claude/agents/
git commit -m "chore(grove): update orchestrator prompt"
git push origin oak/agents           # direct push OK for agents (not protected same way)
# OR: create a PR if human review required (Meta Agent always creates PRs)
```

**Skill addition (automated by Skill Extractor):**
```bash
cd ~/oak-workspaces/skills/          # oak/skills worktree
# Files written to skills/probationary/ by Skill Extractor
git add skills/probationary/
git commit -m "feat(skills): add ETL-join skill"
git push origin oak/skills
```

**UI change (Streamlit Hub):**
```bash
cd ~/oak-workspaces/ui/              # oak/ui worktree
# ... edit app.py or pages/ ...
git add app.py pages/
git commit -m "feat(canopy): add time-series analysis page"
git push origin oak/ui
# Create PR for human review before merging
```

**New problem workspace:**
```bash
bash scripts/new-problem.sh [uuid]   # Creates oak/problem-{uuid} branch + worktree automatically
```

### Anti-patterns (what NOT to do)

- `git commit` on main branch (hook blocks this)
- `git push origin main` (hook blocks this)
- Making agent definition changes in `~/oak/` (main worktree)
- Committing skill files directly to `main`
- Writing to `skills/permanent/` directly (use `SkillRepository.promote()`)

---

## Design Pattern Registry

| Pattern | Module | Status |
|---|---|---|
| Factory | `api/factories/agent_factory.py` | ✅ Stub |
| Strategy | `oak_mcp/oak-api-proxy/strategies.py` | ✅ Stub |
| Observer | `api/events/bus.py` | ✅ Implemented + tested |
| ChainOfResponsibility | `memory/validation_chain.py` | ✅ Implemented + 8 tests |
| Repository | `memory/interfaces.py` | ✅ Interfaces done |
| StateMachine | `api/state_machines/task.py` | ✅ Implemented + tested |
| TemplateMethod | _(Phase 3: agent lifecycle)_ | ⏳ Planned |
| Decorator | _(Phase 3: skill wrapper)_ | ⏳ Planned |
| EventDriven | `api/main.py` + hooks | ✅ Stub |
