# OAK — Orchestrated Agent Kernel

> A self-evolving AI software factory: submit a raw analytical problem, get back a working application. Runs on DGX Spark with local Ollama models — no cloud API required by default.

[![CI](https://github.com/SharathSPhD/oak/actions/workflows/ci.yml/badge.svg)](https://github.com/SharathSPhD/oak/actions/workflows/ci.yml)

## Architecture

Six-layer stack:

```
CANOPY  ── Streamlit Hub (port 8501)          Problem submission + live agent monitoring
TRUNK   ── FastAPI Gateway (port 8000)         REST API, EventBus, WebSocket streams
GROVE   ── Agent Engine (oak-harness)          Claude Code agents in isolated containers
PROXY   ── API Proxy (port 9000)               Routes Claude Code → Ollama (or Claude API)
ROOTS   ── PostgreSQL 16 + pgvector, Redis 7   Schema, skills, episodes, session state
SOIL    ── DGX Spark GB10 (121 GB RAM)         GPU inference via Ollama
```

## Quick Start

### Prerequisites
- Docker 24+ and Docker Compose
- NVIDIA GPU + drivers (DGX/mini mode) or CPU-only (cloud mode)

### Option A: All-in-One (easiest)
```bash
docker run -d --name oak-aio \
  -p 8501:8501 -p 8000:8000 -p 9000:9000 \
  ghcr.io/sharathsphd/oak-aio:latest
```

### Option B: Multi-service (production)
```bash
# Pre-built images — no local builds needed
curl -sL https://raw.githubusercontent.com/SharathSPhD/oak/main/install.sh | bash
```

### Option C: From source
```bash
git clone https://github.com/SharathSPhD/oak.git
cd oak
bash scripts/bootstrap.sh dgx   # or mini or cloud
```

Access:
- **Hub UI**: http://localhost:8501
- **API**: http://localhost:8000
- **API docs**: http://localhost:8000/docs

### Submit a problem
```bash
# Via API
curl -X POST http://localhost:8000/api/problems \
  -H "Content-Type: application/json" \
  -d '{"title": "Sales Analysis", "description": "Analyze Q4 sales CSV...", "tags": ["csv", "analysis"]}'

# Launch agent pipeline
bash scripts/new-problem.sh <problem-uuid>
```

## How It Works

1. **Problem submitted** → stored in PostgreSQL, UUID returned
2. **`new-problem.sh`** → creates git worktree + launches `oak-harness` container
3. **Orchestrator agent** → reads problem, decomposes into tasks, spawns specialists
4. **Specialist agents** (Data Engineer → Data Scientist → ML Engineer) → work in isolated workspace
5. **Judge agent** → runs tests, issues PASS/FAIL verdict (gates task completion)
6. **Skill Extractor** → post-PASS, extracts reusable patterns to `skills/probationary/`
7. **Second run of same type** → skill promoted, reused → faster, cheaper

## Agent Model Routing

| Agent Role | Model | Purpose |
|---|---|---|
| data-engineer, ml-engineer | `qwen3-coder` (default) | ETL, code generation |
| data-scientist, skill-extractor | `deepseek-r1:14b` | Analysis, reasoning |
| orchestrator, judge, meta, architect | `qwen2.5:14b` | Reasoning, synthesis |
| ai-engineer | `qwen3-coder` | LLM features, RAG |
| security-expert | `deepseek-r1:14b` | Security auditing |
| devops, frontend | `qwen3-coder` | Infrastructure, UI |

Override via env: `CODER_MODEL=deepseek-v3 REASONING_MODEL=llama3.3:70b bash scripts/bootstrap.sh dgx`

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
pytest tests/unit/ --cov=api --cov=memory --cov=oak_mcp/oak-api-proxy --cov-report=term-missing
```

## Docker Compose Profiles

```bash
# Unified file with profiles (recommended)
docker compose --profile dgx up -d      # DGX Spark (NVIDIA GPU)
docker compose --profile mini up -d     # Mac Mini M4
docker compose --profile cloud up -d    # Cloud vLLM

# Or use bootstrap script
bash scripts/bootstrap.sh dgx
```

## Documentation

- [User Manual](USER_MANUAL.md) — complete guide, walkthrough, API reference
- [Demo Proof](DEMO_PROOF.md) — live DGX Spark run evidence
- [Spec](spec.md) — system specification
- [PRD](PRD.md) — product requirements
- [Progress](PROGRESS.md) — phase-by-phase development log

## License

MIT
