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

### Status: PLANNED

**Target exit criteria (spec §14):**
- Orchestrator + DE + DS + Judge complete two canonical problems end-to-end
- TaskList + Mailbox fully wired (`api/routers/tasks.py` already exists)
- Judge gate blocks problem completion until verdict = PASS
- `GET /api/judge_verdicts/{problem_uuid}` returns final verdict

**Work items:**
- `api/routers/judge.py` — POST judge verdict, GET by problem_uuid
- `api/services/mailbox.py` — agent-to-agent message passing via Redis
- Orchestrator agent definition that decomposes problems into tasks
- End-to-end test: CSV problem → DE ingest → DS analyse → Judge verdict
- `docker/claude-harness/` hardened per spec §4.6
- Single-agent harness run with CSV-to-app task

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
| TemplateMethod | _(Phase 2: agent lifecycle)_ | ⏳ Planned |
| Decorator | _(Phase 3: skill wrapper)_ | ⏳ Planned |
| EventDriven | `api/main.py` + hooks | ✅ Stub |
