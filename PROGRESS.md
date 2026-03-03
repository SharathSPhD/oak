# OAK Progress Log

## Phase 0 — Walking Skeleton

### Status: IN PROGRESS (completing gap items)

| Exit Criterion | Status | Notes |
|---|---|---|
| `docker compose up` — 4 services healthy | ⏳ Pending | Compose files exist; stack not yet started |
| `psql` shows all 8 schema tables | ⏳ Pending | `schema.sql` exists; init script in progress |
| `POST /api/problems` with CSV → records | ⏳ Pending | Router stub; pipeline in progress (feat/csv-pipeline) |
| CI integration test: 1 CSV → PG table + `app.py` | ⏳ Pending | Integration test being written |
| 25 unit tests passing | ✅ Done | `tests/unit/` — all pass |
| All compose files exist | ✅ Done | `docker/docker-compose.{dgx,mini,cloud,base}.yml` |
| FastAPI app with all 5 routers + WebSocket | ✅ Done | `api/main.py` + `api/routers/` |
| DB schema DDL | ✅ Done | `api/db/schema.sql` — 8 tables + pgvector indexes |
| Memory interfaces (Repository pattern) | ✅ Done | `memory/interfaces.py` |
| Agent definitions | ✅ Done | `.claude/agents/*.md` — 8 agents |
| Hooks (pre/post/task-gate/teammate-idle) | ✅ Done | `.claude/hooks/*.sh` |
| Seed skills (probationary) | ✅ Done | 2 skills in `~/oak-workspaces/skills/probationary/` |
| `__pattern__` CI enforcement | ✅ Done | `tests/conftest.py` + `.github/workflows/ci.yml` |

### Gap Items (feat/* branches in review)
- `feat/validation-chain` — `memory/validation_chain.py` (ChainOfResponsibility, PRD §2.4)
- `feat/api-models` — Complete Pydantic models + router implementations
- `feat/contract-tests` — `tests/contract/` test suite (Phase 1 harness tests)
- `feat/csv-pipeline` — Non-agent CSV→PG→app.py pipeline + integration test + docker init

---

## Phase 1 — Hardened Harness + Single Agent

### Status: PLANNED

**Target exit criteria (spec §14):**
- All harness and proxy unit tests pass in CI
- Single agent inside harness completes CSV-to-app task end-to-end
- Tool proxy correctly blocks all canonical denied commands in tests
- Redis session state survives simulated container restart
- `GET /api/agents/status` shows running agent session accurately

**Work items:**
- Contract tests for `tool-proxy.sh` pattern matching
- Contract tests for `session-state.py` round-trip
- `oak-api-proxy` PassthroughStrategy verified end-to-end
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
| ChainOfResponsibility | `memory/validation_chain.py` | ⏳ In progress (feat/validation-chain) |
| Repository | `memory/interfaces.py` | ✅ Interfaces done |
| StateMachine | `api/state_machines/task.py` | ✅ Implemented + tested |
| TemplateMethod | _(Phase 2: agent lifecycle)_ | ⏳ Planned |
| Decorator | _(Phase 3: skill wrapper)_ | ⏳ Planned |
| EventDriven | `api/main.py` + hooks | ✅ Stub |
