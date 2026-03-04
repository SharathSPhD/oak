# OAK -- Orchestrated Agent Kernel

> A self-evolving AI software factory: submit a raw analytical problem, get back a working application. Runs on DGX Spark with local Ollama models -- no cloud API required by default.

[![CI](https://github.com/SharathSPhD/oak/actions/workflows/ci.yml/badge.svg)](https://github.com/SharathSPhD/oak/actions/workflows/ci.yml)

## Architecture

Seven-layer stack with self-healing daemon:

```
CANOPY  -- React Hub UI (port 8501)          Problem submission + live agent monitoring
TRUNK   -- FastAPI Gateway (port 8000)       REST API, EventBus, WebSocket streams
GROVE   -- Agent Engine (oak-harness)        Claude Code agents in isolated containers
PROXY   -- API Proxy (port 9000)             Routes Claude Code -> Ollama (or Claude API)
DAEMON  -- Self-healing service              Health checks, cleanup, meta-agent triggers
ROOTS   -- PostgreSQL 16 + pgvector, Redis 7 Schema, skills, episodes, session state
SOIL    -- DGX Spark GB10 (121 GB RAM)       GPU inference via Ollama
```

## Quick Start

See [QUICKSTART.md](QUICKSTART.md) for the full guide.

### Prerequisites
- Docker 24+ and Docker Compose v2
- NVIDIA GPU + drivers (DGX/workstation mode) or CPU-only (cloud mode)

### Option A: All-in-One (easiest)
```bash
docker run -d --name oak-aio \
  --gpus all \
  -p 8501:3000 -p 8000:8000 -p 9000:9000 \
  ghcr.io/sharathsphd/oak-aio:latest
```

### Option B: Multi-service (production)
```bash
git clone https://github.com/SharathSPhD/oak.git && cd oak
cp .env.example .env  # Edit with your paths
bash scripts/bootstrap.sh dgx   # or mini or cloud
```

### Option C: Pre-built images
```bash
curl -sL https://raw.githubusercontent.com/SharathSPhD/oak/main/install.sh | bash
```

Access:
- **Hub UI**: http://localhost:8501
- **API**: http://localhost:8000
- **API docs**: http://localhost:8000/docs

## How It Works

1. **Problem submitted** via React UI or API -> stored in PostgreSQL
2. **Pipeline started** -> creates git worktree + launches `oak-harness` container
3. **Orchestrator agent** decomposes problem into tasks, spawns specialists
4. **Specialist agents** (Data Engineer, Data Scientist, ML Engineer) work in isolated workspace
5. **Judge agent** runs tests, issues PASS/FAIL verdict (gates task completion)
6. **Skill Extractor** post-PASS extracts reusable patterns to skill library
7. **Meta Agent** (idle mode) analyzes telemetry and proposes prompt improvements
8. **Self-healing daemon** monitors health, restarts services, cleans orphans

## Agent Model Routing

| Agent Role | Model | Purpose |
|---|---|---|
| data-engineer, ml-engineer | `qwen3-coder` (default) | ETL, code generation |
| data-scientist, skill-extractor | `glm-4.7` | Analysis, reasoning |
| orchestrator, judge, meta, architect | `llama3.3:70b` | Reasoning, synthesis |
| ai-engineer | `qwen3-coder` | LLM features, RAG |
| security-expert | `glm-4.7` | Security auditing |
| devops, frontend | `qwen3-coder` | Infrastructure, UI |

Override via env: `CODER_MODEL=deepseek-v3 bash scripts/bootstrap.sh dgx`

## React Hub UI

The frontend is a production React/Next.js application with:
- **Dashboard** -- system health, quick stats, navigation
- **Submit** -- problem creation with file upload and auto-start
- **Gallery** -- problem list with filters, delete/archive, bulk cleanup
- **Problem Detail** -- tasks, live WebSocket logs, files, judge verdicts
- **Skill Library** -- search, filter, promote probationary skills
- **Telemetry** -- agent metrics, model routing, feature flags
- **Settings** -- system config reference, active agents

## Self-Healing and Self-Improvement

OAK runs a daemon service (`oak-daemon`) that:
- Health-checks all services every 60 seconds
- Restarts crashed containers automatically
- Syncs stale problems (marks exited containers as failed)
- Cleans orphaned harness containers
- Triggers the Meta Agent during idle periods for self-improvement

## Design Patterns

Every production module declares `__pattern__` at module level (CI enforced):

| Pattern | Module | Role |
|---|---|---|
| Configuration | `api/config.py` | Settings management |
| Factory | `api/factories/agent_factory.py` | Agent container lifecycle |
| Observer | `api/events/bus.py` | EventBus subscribers |
| Repository | `memory/skill_repository.py` | Skill library |
| StateMachine | `api/state_machines/task.py` | Task transitions |
| TemplateMethod | `api/lifecycle/agent_lifecycle.py` | Agent lifecycle |
| Decorator | `memory/cached_skills.py` | Skill lookup cache |
| Strategy | `oak_mcp/oak-api-proxy/strategies.py` | Routing strategies |
| ChainOfResponsibility | `memory/validation_chain.py` | Validation chain |

## Development

```bash
# Unit tests (no Docker required)
pytest tests/unit/ -v

# Lint + type check
ruff check api/ memory/ oak_mcp/
mypy --strict api/ memory/

# Coverage
pytest tests/unit/ --cov=api --cov=memory --cov-report=term-missing
```

## Docker Compose Profiles

```bash
docker compose --profile dgx up -d      # DGX Spark (NVIDIA GPU)
docker compose --profile mini up -d     # Mac Mini M4
docker compose --profile cloud up -d    # Cloud vLLM
```

## Documentation

- [Quick Start](QUICKSTART.md) -- get running in 5 minutes
- [User Manual](USER_MANUAL.md) -- complete guide, walkthrough, API reference
- [Spec](spec.md) -- system specification
- [PRD](PRD.md) -- product requirements

## License

MIT
