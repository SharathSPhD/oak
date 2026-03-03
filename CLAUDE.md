# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project Status

OAK is currently in the **specification phase**. `spec.md` (v1.2) and `PRD.md` (v1.0) are the authoritative sources of truth. No implementation code exists yet. All development follows the phased roadmap in `spec.md §14`, starting with Phase 0 (walking skeleton).

Remote repository: `https://github.com/SharathSPhD/oak.git`

---

## Architecture Overview

OAK is a self-evolving AI software factory organised into six layers:

| Layer | Component | Port |
|---|---|---|
| **CANOPY** | Streamlit Hub UI | 8501 |
| **TRUNK** | FastAPI API Gateway | 8000 |
| **GROVE** | Agent Engine (`oak-harness` containers + Claude Code) | — |
| **HARNESS PROXY** | `oak-api-proxy` — routes Claude Code calls to Ollama or Claude API | 9000 |
| **ROOTS** | PostgreSQL 16 + pgvector, Redis 7 | 5432, 6379 |
| **SOIL** | DGX Spark / Mac Mini M4 / Cloud GPU | — |

**Hard rule:** TRUNK and below own all computation and data. The CANOPY UI is a thin REST/WebSocket consumer — it holds no agent logic and no problem data.

### Agent Model

Every Claude Code agent session runs inside an `oak-harness` Docker container. Claude Code is pointed at `oak-api-proxy` (not Ollama directly) via three environment variables — the canonical Ollama + Claude Code integration recipe:

```bash
ANTHROPIC_BASE_URL=http://oak-api-proxy:9000
ANTHROPIC_AUTH_TOKEN=ollama
ANTHROPIC_API_KEY=                    # Intentionally empty; proxy manages escalation
```

The proxy routes calls to local Ollama by default (`ROUTING_STRATEGY=passthrough`). Stall-based Claude API escalation is opt-in (`STALL_DETECTION_ENABLED=true`) and disabled in v1.

### Git Worktree Structure

OAK uses Git worktrees — one per concern, one per problem. See `PROGRESS.md` for full workflow examples.

| Branch | Worktree path | Concern | Who commits here |
|---|---|---|---|
| `main` | `~/oak/` | Core: API, memory, docker, scripts, tests | Feature PRs only — never direct commits |
| `oak/agents` | `~/oak-workspaces/agents/` | Agent definitions (`.claude/agents/*.md`), hooks | Meta Agent (via PR) |
| `oak/skills` | `~/oak-workspaces/skills/` | Skill library (`permanent/`, `probationary/`) | Skill Extractor Agent (automated) |
| `oak/ui` | `~/oak-workspaces/ui/` | Streamlit Hub (`app.py`, `pages/`) | Software Architect (via PR) |
| `oak/problem-{uuid}` | `~/oak-workspaces/problem-{uuid}/` | Per-problem solution code | Problem agents |

**Never commit directly to `main`.** Use feature branches + PRs for all core changes. Problem code lives on `oak/problem-{uuid}` branches only.

---

## Key Commands

### Bootstrap (first time on a new node)
```bash
bash scripts/bootstrap.sh        # Full DGX setup: builds harness + proxy, pulls models, starts stack
```

### Docker stack
```bash
# DGX Spark (primary)
docker compose -f docker/docker-compose.dgx.yml up -d oak-postgres oak-redis oak-ollama oak-api-proxy oak-api oak-ui

# Mac Mini M4
docker compose -f docker/docker-compose.mini.yml up -d ...

# Build harness images before first run
docker build -t oak/api-proxy:latest ./oak_mcp/oak-api-proxy/
docker build -t oak/harness:latest ./docker/claude-harness/
```

### Start a new problem
```bash
bash scripts/new-problem.sh [problem-uuid]   # Creates worktree + launches orchestrator in harness
```

### Verify the routing chain
```bash
# Proxy → Ollama
curl -s -H "Authorization: Bearer ollama" http://localhost:9000/v1/models | python3 -c "import sys,json; d=json.load(sys.stdin); print([m['id'] for m in d.get('data',[])])"

# Direct Ollama (diagnostics only)
curl -s http://localhost:11434/api/tags
```

### Pull Ollama models
```bash
docker exec oak-ollama ollama pull qwen3-coder   # Primary: all coding tasks
docker exec oak-ollama ollama pull glm-4.7        # Analysis/EDA
docker exec oak-ollama ollama pull llama3.3:70b   # Reasoning/synthesis
docker exec oak-ollama ollama pull deepseek-v3    # ML scripting
```

### Tests
```bash
# Unit tests (no I/O, all external mocked)
pytest tests/unit/ -v

# Integration tests (requires test containers: real PG + Redis, no Docker-in-Docker)
pytest tests/integration/ -v

# Contract tests (harness + proxy behaviour)
pytest tests/contract/ -v

# Run a single test file
pytest tests/unit/test_task_state_machine.py -v

# Run a single test by name
pytest tests/unit/test_task_state_machine.py::test_task_state_machine__pending_to_complete_direct__raises_illegal_transition -v

# Smoke tests (requires docker compose --profile test up)
pytest tests/smoke/ -v

# System tests (full stack, Phase 3+)
pytest tests/system/ -v

# Coverage
pytest tests/unit/ --cov=api --cov=memory --cov=oak_mcp/oak-api-proxy --cov-report=term-missing
```

### Linting and type checking
```bash
ruff check api/ memory/ oak_mcp/          # Linting (includes C901 cyclomatic complexity)
mypy --strict api/ memory/                # Type checking (required Phase 1+)
pydocstyle api/ memory/                   # Docstring coverage
```

---

## Implementation Rules (from PRD.md)

### 1. Design Patterns First
Every production module **must** declare `__pattern__` at module level before any other code:
```python
__pattern__ = "Repository"   # or Factory, Strategy, Observer, StateMachine, etc.
```
The `conftest.py` fixture fails test collection for any production module missing this attribute. Declared patterns: Factory, Strategy, Observer, ChainOfResponsibility, Repository, StateMachine, TemplateMethod, Decorator, EventDriven.

### 2. Test-Driven Development (strict)
Red → Green → Refactor. No production code before a failing test. PRs are rejected if production code lacks a corresponding test. Test naming convention:
```
test_{unit_under_test}__{condition}__{expected_outcome}
```

### 3. Configuration-Driven
`api/config.py` is the **only** file that reads `os.environ`. All other code imports `from api.config import settings`. Direct `os.environ` access elsewhere is a `ruff` violation and a CI blocker. All configuration lives in `OAKSettings` (Pydantic `BaseSettings`). Adding a new platform target never requires a code change — only a new `.env.{profile}` file.

### 4. Hooks Are Thin Relays
Each `.claude/hooks/*.sh` script does exactly one thing: POST a serialised `AgentEvent` to `http://oak-api:8000/internal/events`. All business logic lives in Python `EventSubscriber` classes. A hook with >10 lines of logic is a violation.

### 5. Skill Promotion Is Gated
Skills write to `skills/probationary/` only. Promotion to `skills/permanent/` goes exclusively through `SkillRepository.promote()`, which enforces `OAK_SKILL_PROMO_THRESHOLD` (default: 2 independent problems). Never write directly to `permanent/`.

### 6. Anti-Patterns (forbidden)
- **God Orchestrator**: Orchestrator only decomposes problems and spawns agents. State transitions, events, and skill promotion belong in their respective components.
- **Inline routing conditionals**: All routing decisions live in a named `RoutingStrategy` subclass; the proxy's `proxy()` function never changes.
- **Direct `os.environ` access** outside `api/config.py`.
- **Fat hooks**: hooks call the API; Python classes do the work.
- **Probationary skill bypass**: no direct writes to `permanent/`.

---

## Phase Roadmap (build in order)

| Phase | Scope | Key exit criteria |
|---|---|---|
| **0** | Walking skeleton: PG + Redis + Ollama + FastAPI + static CSV→app, no agents | All 4 services healthy; schema verified; non-agent CSV→app pipeline passes CI |
| **1** | Hardened harness + single agent + proxy unit tests | All contract tests pass; tool-proxy blocks all deny patterns; session round-trips container restart |
| **2** | Agent teams + task list + mailbox + Judge gate | Orchestrator + DE + DS + Judge complete two canonical problems end-to-end |
| **3** | Memory + skill library + Hub | Skill extracted from Problem 1 reused on Problem 2; Hub live on Streamlit Cloud |
| **4** | Mac Mini port + stall detection calibration | Full lifecycle on `OAK_MODE=mini`; stall escalation rate < 30% |
| **5** | Concurrency + cloud + vLLM | 3 concurrent problems; zero cross-problem leakage |

---

## PostgreSQL Schema Tables

`problems`, `tasks`, `mailbox`, `episodes` (pgvector 1536-dim), `skills` (pgvector), `agent_telemetry`, `judge_verdicts`

Full DDL: `api/db/schema.sql` (to be created in Phase 0).

---

## Environment Variables

Platform selection: set `OAK_MODE=dgx|mini|cloud` and use the matching compose file. All other values have validated defaults in `OAKSettings`. See `PRD.md §4.7` for the full configuration reference table.

**Security:** `.env` must be in `.gitignore`. Never commit real API keys. `ANTHROPIC_API_KEY_REAL` (the real Anthropic key used by the proxy for escalation) is never logged and never returned by `/health`.

---

## MCP Servers

Defined in `.claude/mcp.json` (to be created): `filesystem`, `postgres`, `git`, `oak-memory` (pgvector retrieval), `oak-skills` (skill library lookup). Agents access PostgreSQL only through MCP — never via direct `psql` from agent containers.

---

## Commit Message Format

```
type(scope): subject

body (optional)

Refs: #issue_number
```

Types: `feat`, `fix`, `test`, `refactor`, `chore`, `docs`
Scopes: `trunk`, `grove`, `harness`, `proxy`, `memory`, `canopy`, `skills`, `config`
