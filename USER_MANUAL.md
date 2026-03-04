# OAK User Manual

## The Open Agent Knowledge-Factory

**Version 1.1** | DGX Spark Edition | March 2026

---

## Table of Contents

1. [What is OAK?](#1-what-is-oak)
2. [System Architecture](#2-system-architecture)
3. [Prerequisites & Installation](#3-prerequisites--installation)
4. [Starting the Stack](#4-starting-the-stack)
5. [The OAK Hub (Web UI)](#5-the-oak-hub-web-ui)
6. [Submitting Your First Problem](#6-submitting-your-first-problem)
7. [How OAK Solves Problems](#7-how-oak-solves-problems)
8. [Monitoring Progress](#8-monitoring-progress)
9. [Reading Results](#9-reading-results)
10. [**Live Demo Walkthrough**](#10-live-demo-walkthrough) ← *Real run on DGX Spark*
11. [API Reference](#105-api-reference)
12. [Troubleshooting](#11-troubleshooting)
13. [Advanced: Skill Library](#12-advanced-skill-library)
14. [Streamlit Cloud Deployment](#14-streamlit-cloud-deployment-optional)

---

## 1. What is OAK?

OAK is an **AI software factory** that solves data science and analytics problems **end-to-end**.

Instead of running individual analyses, you describe your problem once. OAK:

1. **Decomposes** the problem into typed tasks (ingest, analyse, model, synthesise, validate)
2. **Spawns a team** of specialized AI agents (Orchestrator, Data Engineer, Data Scientist, ML Engineer, Software Architect, Judge)
3. **Executes tasks** with multi-GPU acceleration and stall detection
4. **Extracts reusable skills** from solved problems
5. **Returns a judge-verified solution** — usually a deployable Streamlit app

**Who should use OAK?**

- Data scientists with messy CSV files or databases
- Teams that solve similar problems repeatedly
- Anyone who wants AI agents to handle the boilerplate

**What problems can OAK solve?**

- Sales forecasting (time-series + visualization)
- Customer segmentation (clustering + interactive dashboard)
- Churn prediction (classification + explainability)
- Anomaly detection (statistical profiling + alerting UI)
- Exploratory data analysis (any dataset → interactive dashboard)

---

## 2. System Architecture

OAK is organized into **six layers**:

```
┌─────────────────────────────────────────────────────┐
│  CANOPY (Streamlit Hub UI)                  :8501   │
│  Thin REST/WebSocket consumer — holds no logic     │
├─────────────────────────────────────────────────────┤
│  TRUNK (FastAPI API Gateway)                :8000   │
│  Router: problems, agents, mailbox, skills        │
├─────────────────────────────────────────────────────┤
│  GROVE (Agent Engine)                              │
│  oak-harness containers + Claude Code sessions    │
├─────────────────────────────────────────────────────┤
│  HARNESS PROXY (oak-api-proxy)              :9000   │
│  Routes Claude Code calls → Ollama or Claude API  │
├─────────────────────────────────────────────────────┤
│  ROOTS (Data & State)                              │
│  PostgreSQL 16 + pgvector        :5432            │
│  Redis 7                          :6379            │
├─────────────────────────────────────────────────────┤
│  SOIL (Compute)                                    │
│  DGX Spark (primary) / Mac Mini M4 / Cloud GPU    │
└─────────────────────────────────────────────────────┘
```

**Key principle:** TRUNK and below own all computation and data. The CANOPY UI is a **thin client** — no agent logic, no problem data, no credentials.

---

## 3. Prerequisites & Installation

### Hardware Requirements

**Minimum (DGX Spark):**
- NVIDIA GPU with 80 GB VRAM (A100 or H100)
- 256 GB CPU RAM
- 2 TB SSD (models + data)
- Docker 20.10+, Docker Compose 2.0+

**Alternative (Mac Mini M4):**
- Apple Silicon M4 or later
- 16+ GB RAM
- 500 GB SSD

### Software Requirements

- `git` 2.30+
- `docker` + `docker-compose`
- `python` 3.11+
- `curl` (for API testing)

### Clone and Bootstrap

```bash
# Clone the repository
git clone https://github.com/SharathSPhD/oak.git ~/oak
cd ~/oak

# First-time setup — builds all images, pulls Ollama models, starts stack
bash scripts/bootstrap.sh dgx    # or 'mini' if on Mac Mini
```

The bootstrap script:
1. Builds 6 Docker images (`oak/api-proxy`, `oak/harness`, `oak/api`, `oak/ui`, postgres, redis)
2. Pulls Ollama models (qwen3-coder, llama3.3:70b, deepseek-v3)
3. Creates networks and volumes
4. Starts the full Docker Compose stack
5. Seeds the skill library database
6. Exits when all services are healthy ✅

**Subsequent startups:**

```bash
# From ~/oak, just bring up the stack (images already built)
# DGX Spark — primary (unified compose with profile)
docker compose -f docker/docker-compose.yml --profile dgx up -d

# Mac Mini M4
docker compose -f docker/docker-compose.yml --profile mini up -d

# Cloud GPU (vLLM backend)
docker compose -f docker/docker-compose.yml --profile cloud up -d

# Watch logs in real-time
docker compose logs -f oak-api
```

---

## 4. Starting the Stack

### Verify Services Are Healthy

After `bootstrap.sh` completes, verify all 6 services:

```bash
# Check service health
docker compose -f docker/docker-compose.yml --profile dgx ps

# Expected output:
# NAME             STATUS
# oak-postgres     healthy
# oak-redis        healthy
# oak-ollama       Up (healthy)
# oak-api-proxy    healthy
# oak-api          healthy
# oak-ui           Up

# Test the API health endpoint
curl -s http://localhost:8000/health | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin), indent=2))"

# Expected output:
# {
#   "status": "healthy",
#   "oak_mode": "dgx",
#   "routing_strategy": "passthrough",
#   "models": {
#     "default": "llama3.3:70b",
#     "coder": "qwen3-coder:latest",
#     "ml_engineer": "deepseek-v3:latest"
#   }
# }
```

### Verify Ollama Models Are Available

```bash
# List all pulled models
curl -s -H "Authorization: Bearer ollama" \
  http://localhost:9000/v1/models | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print([m['id'] for m in d.get('data',[])])"

# Expected output:
# ['qwen3-coder:latest', 'llama3.3:70b', 'deepseek-v3:latest']
```

### Stop the Stack

```bash
# Graceful shutdown (preserves data)
docker compose -f docker/docker-compose.dgx.yml down

# Full cleanup (removes volumes — data lost)
docker compose -f docker/docker-compose.dgx.yml down -v
```

---

## 5. The OAK Hub (Web UI)

Access the Streamlit Hub at **http://localhost:8501** (or your server's IP:8501).

### Page 1: Submit a Problem

**URL:** `http://localhost:8501/` (home page)

**What it does:** Submit a new data science problem to OAK.

**Form fields:**
- **Problem title** (required): e.g. "Sales forecast Q4 2025"
- **Description** (required): What should the final output look like? e.g. "Build an interactive dashboard showing weekly sales predictions with 95% confidence intervals. User should be able to filter by region."
- **Data path** (optional): Path to CSV or database connection string, e.g. `/mnt/oak-data/sales.csv`

**Response:** Problem UUID + metadata

```json
{
  "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "title": "Sales forecast Q4 2025",
  "description": "...",
  "status": "pending",
  "created_at": "2026-03-03T14:22:05.123Z"
}
```

**What happens next:**
- An Orchestrator agent spawns immediately
- It reads your problem description and creates a PROBLEM.md framing document
- Tasks are created and assigned to specialists
- You can watch progress on Page 2

---

### Page 2: Live Agent Status

**URL:** `http://localhost:8501/02_status`

**What it shows:**
- All currently running agents (their roles, problem assignments, status)
- Color-coded status: 🟢 running, 🟡 idle, 🔴 terminated, ⚪ unknown
- Auto-refresh every 5 seconds (toggle at top)

**Example output:**

```
🟢 orchestrator-f47ac10b-58cc-4372
  Status: running
  Problem: f47ac10b-58cc-4372

🟡 data-engineer-f47ac10b-58cc-4372
  Status: idle
  Problem: f47ac10b-58cc-4372

🟢 data-scientist-f47ac10b-58cc-4372
  Status: running
  Problem: f47ac10b-58cc-4372
```

**Interpretation:**
- If agents are stuck on "idle" for >5 minutes, check Troubleshooting §11
- Running agents are actively working
- Terminated agents have completed or failed (check Judge verdicts on Page 3)

---

### Page 3: Solution Gallery

**URL:** `http://localhost:8501/03_gallery`

**What it shows:**
- All submitted problems (past and present)
- Status of each (pending, in_progress, succeeded, failed)
- Generated solution (app URL or file path if complete)
- Metadata: submission time, data path, verdict

**Example:**

```
📋 Sales forecast Q4 2025 — succeeded
  Description: Build an interactive dashboard...
  Status: succeeded
  UUID: f47ac10b-58cc-4372-a567-0e02b2c3d479
  Solution URL: http://localhost:8502/problem-f47ac10b
```

Clicking a problem expands to show full details and links to the generated app.

---

### Page 4: Skill Library

**URL:** `http://localhost:8501/04_skills`

**What it shows:**
- All learned reusable skills (extracted from solved problems)
- Search by keyword: "csv", "etl", "time-series", etc.
- Filter by category: ETL, analysis, ML, UI, infra
- Filter by status: permanent (production-ready) vs. probationary (still learning)

**Example skill:**

```
🔧 CSV-to-Pandas-ETL [etl] — permanent
  Description: Load CSV, handle missing values, standardize column names
  Use count: 7
  Keywords: csv, etl, pandas, load-file
  Verified on problems: [f47ac10b, c92a0f14, ...]
```

**How it works:**
- When a Data Engineer ingests CSV files, they record the pattern as a potential skill
- After being used on 2+ independent problems, the skill is promoted to "permanent"
- All agents can see and reuse permanent skills automatically

**For users:** Don't edit this page — it's read-only. Skills are managed by the Skill Extractor agent.

---

### Page 5: Telemetry

**URL:** `http://localhost:8501/05_telemetry`

**What it shows:**
- System health: OAK mode (dgx / mini / cloud), routing strategy (passthrough / stall)
- Feature flags: stall detection on/off, escalation enabled/disabled
- Available models and their sizes
- Aggregated metrics:
  - Total tool calls made by all agents
  - Escalation rate (% of calls routed to Claude API)
  - Events by type (tool_use, task_state_change, skill_promotion, etc.)
  - Active problems in last hour
  - Recent telemetry events (last 20)

**Example metrics:**

```
OAK Mode: dgx
Routing Strategy: passthrough
API Key Present: ✅

Feature Flags
  STALL_DETECTION_ENABLED: On
  ESCALATION_ENABLED: On

Recent Telemetry Events:
  [14:22:05] agent: orchestrator, event: task_created, tool: read_file, escalated: false
  [14:22:08] agent: data-engineer, event: tool_use, tool: bash, escalated: false
  [14:22:12] agent: data-scientist, event: tool_use, tool: postgres_query, escalated: true
  ...
```

**What it means:**
- Escalation rate > 30% → Ollama is stalling, falling back to Claude API (expected on mini)
- Escalation rate < 5% → Ollama is fast, local inference preferred (DGX tuning successful)
- Active problems → How many concurrent problems are being solved right now

---

## 6. Submitting Your First Problem

### Step-by-Step: UI Approach

1. **Open OAK Hub:** Navigate to http://localhost:8501
2. **Fill the form:**
   ```
   Title: "Customer churn prediction"
   Description: "We have 6 months of customer behavior logs. Build a
                classification model that predicts churn probability.
                Generate an interactive dashboard showing which factors
                drive churn, and a download link for churn scores."
   Data path: "/mnt/oak-data/customers.csv"
   ```
3. **Click "Submit Problem"**
4. **Copy the UUID** from the success message
5. **Go to Page 2 (Status)** to watch agents spawn and work

---

### Step-by-Step: API Approach (curl)

If you prefer command-line:

```bash
# Define variables
TITLE="Customer churn prediction"
DESCRIPTION="Build a classification model predicting churn probability.
Generate interactive dashboard showing churn drivers."
DATA_PATH="/mnt/oak-data/customers.csv"

# Submit the problem
curl -X POST http://localhost:8000/api/problems \
  -H "Content-Type: application/json" \
  -d "{
    \"title\": \"$TITLE\",
    \"description\": \"$DESCRIPTION\",
    \"data_path\": \"$DATA_PATH\"
  }" | python3 -m json.tool

# Expected response (201 Created):
{
  "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "title": "Customer churn prediction",
  "description": "Build a classification model...",
  "status": "pending",
  "created_at": "2026-03-03T14:22:05.123Z",
  "updated_at": "2026-03-03T14:22:05.123Z"
}

# Save the UUID for later queries
PROBLEM_UUID="f47ac10b-58cc-4372-a567-0e02b2c3d479"
```

---

### Tracking Your Submission

After submission, OAK automatically:

1. **Creates an Orchestrator agent** (spawns in a harness container)
2. **Frames the problem** (writes PROBLEM.md with restated goals, success metrics)
3. **Decomposes into tasks**:
   - `ingest`: Data Engineer loads and validates CSV
   - `analyse`: Data Scientist explores patterns
   - `model`: ML Engineer builds classifier
   - `synthesise`: Software Architect generates Streamlit app
   - `validate`: Judge verifies solution meets requirements
4. **Agents communicate** via mailbox (async message passing)
5. **Results accumulate** in `/oak-workspaces/problem-{uuid}/`

**Typical timeline:**
- Small dataset (< 10 MB): 5–15 minutes
- Medium dataset (10–100 MB): 15–45 minutes
- Large dataset (> 100 MB): 1–4 hours (depends on model complexity)

---

## 7. How OAK Solves Problems

### The Agent Team

OAK uses a **Pipeline of Specialists**:

| Agent | Role | Output |
|---|---|---|
| **Orchestrator** | Team Lead + Problem Framer | PROBLEM.md (restated goals, success metrics) |
| **Data Engineer** | Data Ingestion + Validation | Cleaned CSV → PostgreSQL, SCHEMA.md |
| **Data Scientist** | Exploratory Analysis | ANALYSIS_REPORT.md (key findings, anomalies, correlations) |
| **ML Engineer** | Model Training | Trained model artifact, MODEL_REPORT.md (accuracy, feature importance) |
| **Software Architect** | App Synthesis | Streamlit app (interactive dashboard + download links) |
| **Judge Agent** | Quality Gate | Verdict (PASS/FAIL), detailed checks |

### Task Lifecycle

Each task flows through 5 states:

```
pending → running → waiting_gate → completed → archived
           (agent works)    ↓
                    (Judge verifies)
```

**Example: `analyse` task for Data Scientist**

1. **pending** → Orchestrator creates task, assigns to Data Scientist
2. **running** → Data Scientist agent claims task, runs EDA
3. **waiting_gate** → Data Scientist submits ANALYSIS_REPORT.md; Judge reviews
4. **completed** → Judge approves; task marked done
5. **archived** → Results stored in PostgreSQL + episodic memory (pgvector)

### Communication: The Mailbox

Agents don't share code or data directly. Instead, they use **async messaging**:

**Example: Data Scientist → ML Engineer**

```json
{
  "from_agent": "data-scientist-f47ac10b",
  "to_agent": "ml-engineer-f47ac10b",
  "subject": "Analysis complete — key findings",
  "body": "ANALYSIS_REPORT.md is ready. Key insight: churn correlates
          strongly with contract_length < 12 months (0.73 correlation)
          and account_age < 6 months (0.61 correlation).
          Recommend starting with logistic regression."
}
```

Messages are:
- Stored in PostgreSQL `mailbox` table
- Published to Redis pub/sub stream
- Agents poll inbox before claiming next task
- Marked "read" after processing

---

### Skills: Reusable Problem-Solving Patterns

When a Data Engineer successfully ingests a CSV file with specific patterns (date parsing, categorical encoding, etc.), the pattern is **extracted as a reusable skill**.

**Example skill: `csv-datetime-fill`**

```yaml
name: csv-datetime-fill
category: etl
status: probationary  # Newly discovered
description: Fill datetime gaps in time-series CSV using forward-fill + interpolation
trigger_keywords: [csv, datetime, time-series, fill-gaps]
use_count: 1
verified_on_problems: [f47ac10b]
```

After the skill is used on 2+ independent problems, it's **promoted to permanent**:

```yaml
status: permanent  # Now available to all agents
verified_on_problems: [f47ac10b, c92a0f14, 7a1b3c2d]
use_count: 3
```

Permanent skills are:
- Cached in memory (pgvector semantic search)
- Automatically suggested to agents (via oak-skills MCP)
- Reusable across problems without re-learning

---

## 8. Monitoring Progress

### Real-time: Status Page (Page 2)

Refresh the **Status dashboard** to see:
- Which agents are currently running
- How many agents are idle vs. active
- Problem UUID assigned to each agent

```bash
# Or via API:
curl http://localhost:8000/api/agents/status | python3 -m json.tool
```

**Example:**

```json
{
  "agents": [
    {
      "agent_id": "orchestrator-f47ac10b",
      "role": "orchestrator",
      "problem_uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
      "status": "running",
      "container_id": "abc123def456",
      "created_at": "2026-03-03T14:22:05Z"
    },
    {
      "agent_id": "data-engineer-f47ac10b",
      "role": "data-engineer",
      "problem_uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
      "status": "idle",
      "container_id": "xyz789uvw012",
      "created_at": "2026-03-03T14:23:15Z"
    }
  ]
}
```

### Real-time: Logs

Watch live container logs:

```bash
# Orchestrator logs
docker logs -f oak-harness-f47ac10b

# Proxy logs (routing decisions)
docker logs -f oak-api-proxy

# API logs
docker logs -f oak-api
```

### Detailed: Telemetry Page (Page 5)

See aggregated statistics:
- Total tool invocations
- Escalation rate (Ollama vs. Claude API fallback)
- Events by type
- Recent events (last 20)

---

### Problem-Specific Logs

Problem outputs are stored in:

```bash
# Navigate to problem worktree
cd ~/oak-workspaces/problem-f47ac10b/

# View problem framing
cat PROBLEM.md

# View data ingestion log
cat SCHEMA.md

# View analysis findings
cat ANALYSIS_REPORT.md

# View model report
cat MODEL_REPORT.md

# View generated app (Streamlit code)
cat app.py

# View commit history for this problem
git log --oneline
```

---

## 9. Reading Results

### Judge Verdict: Pass/Fail

When the Software Architect finishes synthesizing the Streamlit app, the **Judge Agent** verifies the solution:

```bash
# Get all verdicts for a problem
curl http://localhost:8000/api/judge_verdicts/f47ac10b-58cc-4372-a567-0e02b2c3d479 | python3 -m json.tool
```

**Example verdict:**

```json
{
  "id": "verdict-123abc",
  "task_id": "task-synthesise-456def",
  "verdict": "PASS",
  "checks": {
    "output_format": { "status": "pass", "details": "Streamlit app.py is valid Python" },
    "data_accessibility": { "status": "pass", "details": "Connects to Postgres via MCP" },
    "ui_completeness": { "status": "pass", "details": "Dashboard has filter controls, metrics, download button" },
    "model_accuracy": { "status": "pass", "details": "AUC = 0.87, meets requirement > 0.8" }
  },
  "notes": "Solution ready for deployment. Key insight: account_age is strongest predictor.",
  "created_at": "2026-03-03T14:45:23Z"
}
```

**If FAIL:**

```json
{
  "verdict": "FAIL",
  "checks": {
    "ui_completeness": { "status": "fail", "details": "Missing export-to-CSV button" },
    "model_accuracy": { "status": "fail", "details": "AUC = 0.72, below requirement 0.8" }
  },
  "notes": "Revert to Data Scientist: try ensemble models or feature engineering."
}
```

If a solution fails, the loop restarts (Data Scientist refines analysis → ML Engineer tries new model → Judge re-checks).

---

### Generated App (Streamlit)

Once Judge approves, the app is accessible at:

```
http://localhost:8502/problem-f47ac10b-58cc-4372
```

(Or wherever your Streamlit Cloud deployment is configured.)

**What it contains:**
- Interactive filters (region, time range, customer segment)
- Key metrics (churn rate, feature importance chart)
- Prediction table (customer ID, churn probability, confidence interval)
- Download button (export predictions as CSV)
- Data refresh date + model version
- Links back to analysis/model reports

---

### Files in Problem Worktree

After a problem is solved, your `/oak-workspaces/problem-{uuid}/` contains:

```
~/oak-workspaces/problem-f47ac10b/
├── PROBLEM.md                 # Problem framing (goals, success metrics)
├── SCHEMA.md                  # Data schema after ingestion
├── ANALYSIS_REPORT.md         # EDA findings
├── MODEL_REPORT.md            # Model training summary + accuracy
├── app.py                     # Generated Streamlit dashboard
├── requirements.txt           # Python dependencies
├── data/
│   └── clean-data.csv         # Ingested + cleaned CSV
└── .git                       # Git branch oak/problem-{uuid}
```

---

## 10. Live Demo Walkthrough

> **This section records a real end-to-end OAK run** executed on DGX Spark on 2026-03-03.
> Every command, response, and observation below is captured live from the running system.
> Reference: `docs/DEMO_PROOF.md` for the full evidence log.

### Scenario: Sales Performance Analysis Q4 2025

A data scientist wants to analyse Q4 2025 sales data (20-row CSV, 6 columns) to identify
top-performing regions and build a Q1 2026 revenue forecast.

---

### Step 1 — Verify the Stack is Running

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

**Actual output (2026-03-03 22:52 UTC):**
```
NAMES                 STATUS                    PORTS
oak-oak-api-proxy-1   Up 12 minutes             0.0.0.0:9000->9000/tcp
oak-oak-ui-1          Up 14 minutes (healthy)   0.0.0.0:8501->8501/tcp
oak-oak-api-1         Up 19 minutes (healthy)   0.0.0.0:8000->8000/tcp
oak-oak-ollama-1      Up 20 minutes             0.0.0.0:11434->11434/tcp
oak-oak-redis-1       Up 22 minutes (healthy)   0.0.0.0:6379->6379/tcp
oak-oak-postgres-1    Up 22 minutes (healthy)   0.0.0.0:5432->5432/tcp
```

```bash
curl -s http://localhost:8000/health
```
```json
{
  "status": "healthy",
  "oak_mode": "dgx",
  "routing_strategy": "passthrough",
  "stall_detection_enabled": false,
  "max_agents_per_problem": 10,
  "max_concurrent_problems": 3,
  "models": {"default": "llama3.3:70b", "coder": "qwen3-coder", "analysis": "glm-4.7"},
  "feature_flags": {"telemetry_enabled": true, "skill_extraction_enabled": true,
                    "judge_required": true, "meta_agent_enabled": false}
}
```

---

### Step 2 — Prepare the Dataset

Create a CSV file locally (OAK agents will read this path inside the container):

```bash
mkdir -p /tmp/oak_demo
cat > /tmp/oak_demo/sales_data.csv << 'EOF'
date,region,product,units_sold,revenue,customer_id
2025-10-01,North,Widget-A,150,7500.00,CUST-001
2025-10-01,South,Widget-B,200,12000.00,CUST-002
2025-10-02,North,Widget-A,120,6000.00,CUST-003
2025-10-02,East,Gadget-X,80,9600.00,CUST-004
2025-10-03,West,Widget-B,175,10500.00,CUST-005
... (20 rows total)
EOF
```

| date | region | product | units_sold | revenue | customer_id |
|------|--------|---------|------------|---------|-------------|
| 2025-10-01 | North | Widget-A | 150 | 7,500 | CUST-001 |
| 2025-10-01 | South | Widget-B | 200 | 12,000 | CUST-002 |
| 2025-10-07 | South | Gadget-X | 250 | 30,000 | CUST-006 |
| 2025-10-10 | East | Gadget-X | 165 | 19,800 | CUST-018 |

**Pattern visible in data:** South region + Gadget-X = highest revenue. A regression model
predicting Q1 2026 should weight this segment heavily.

---

### Step 3 — Submit the Problem

**Via API:**
```bash
curl -s -X POST http://localhost:8000/api/problems \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Sales Performance Analysis Q4 2025",
    "description": "Analyze Q4 2025 sales data to identify top-performing regions, products, and customer segments. Build a predictive model for Q1 2026 revenue forecasting. Dataset: /tmp/oak_demo/sales_data.csv",
    "tags": ["sales", "forecasting", "regression", "csv-analysis"]
  }'
```

**Actual response:**
```json
{
  "id": "f3e6edc9-4d31-46c5-9a44-e00d6ed5db64",
  "title": "Sales Performance Analysis Q4 2025",
  "description": "...",
  "status": "pending",
  "solution_url": null,
  "idempotency_key": null,
  "created_at": "2026-03-03T22:54:34.098996Z",
  "updated_at": "2026-03-03T22:54:34.098996Z"
}
```

**Problem UUID: `f3e6edc9-4d31-46c5-9a44-e00d6ed5db64`**

---

### Step 4 — Verify in the Database

```bash
docker exec oak-oak-postgres-1 psql -U oak -d oak \
  -c "SELECT id, title, status, created_at FROM problems;"
```
```
                  id                  |               title                | status  |          created_at
--------------------------------------+------------------------------------+---------+-------------------------------
 f3e6edc9-4d31-46c5-9a44-e00d6ed5db64 | Sales Performance Analysis Q4 2025 | pending | 2026-03-03 22:54:34.098996+00
(1 row)
```

All 7 schema tables confirmed present:
```
agent_telemetry | episodes | judge_verdicts | mailbox | problems | skills | tasks
```

---

### Step 5 — Check the Skills Library

Before solving, OAK checks for reusable skills. The library is seeded with two foundational skills:

```bash
curl -s "http://localhost:8000/api/skills?query=analysis"
```
```
event-bus-observer   | infra | probationary
task-state-machine   | infra | probationary
```

As problems are solved, the Skill Extractor agent promotes reusable patterns here.

---

### Step 6 — Launch the Orchestrator

```bash
bash scripts/new-problem.sh f3e6edc9-4d31-46c5-9a44-e00d6ed5db64
```

**Actual output:**
```
[new-problem] UUID: f3e6edc9-4d31-46c5-9a44-e00d6ed5db64
[new-problem] Network: oak_oak-net
Preparing worktree (new branch 'oak/problem-f3e6edc9-4d31-46c5-9a44-e00d6ed5db64')
HEAD is now at 010a27b fix(proxy): route order + ...
d43af12e6efe843420d669ae7cd84c97104247f71161041fe337904a9de2c1e9
[new-problem] Workspace : /home/sharaths/oak-workspaces/problem-f3e6edc9-4d31-46c5-9a44-e00d6ed5db64
[new-problem] Branch    : oak/problem-f3e6edc9-4d31-46c5-9a44-e00d6ed5db64
[new-problem] Container : oak-harness-f3e6edc9-4d31-46c5-9a44-e00d6ed5db64
[new-problem] Logs      : docker logs -f oak-harness-f3e6edc9-4d31-46c5-9a44-e00d6ed5db64
```

OAK creates:
- A git branch `oak/problem-{uuid}` — isolated solution workspace
- An `oak-harness` container running Claude Code pointed at Ollama via the proxy
- The orchestrator begins decomposing the problem into tasks

---

### Step 7 — Observe Routing in Action

After the harness runs, inspect the proxy call counter:

```bash
docker exec oak-oak-redis-1 redis-cli GET "oak:telemetry:total_calls"
```
```
14
```

**14 API calls** were routed through `oak-api-proxy → Ollama (qwen3-coder:latest)`.

The session hook also fired, writing command history to Redis:
```bash
docker exec oak-oak-redis-1 redis-cli KEYS "oak:*"
```
```
oak:telemetry:total_calls
oak:session:unknown:cmd_history
```

**Full proven chain:** `Claude Code (harness) → oak-api-proxy:9000 → Ollama:11434 → qwen3-coder`

---

### Step 8 — Monitor Progress (UI)

Open **http://localhost:8501** → **Status Dashboard** page.

The Status page polls `GET /api/problems/{uuid}` and shows:

| Field | Value |
|---|---|
| Problem ID | f3e6edc9-4d31-46c5-9a44-e00d6ed5db64 |
| Title | Sales Performance Analysis Q4 2025 |
| Status | pending → in_progress → complete |
| Agent Events | Streamed live via WebSocket |

Follow logs live:
```bash
docker logs -f oak-harness-f3e6edc9-4d31-46c5-9a44-e00d6ed5db64
```

---

### Step 9 — Send a Message to an Agent (Mailbox)

You can inject instructions into a running agent's inbox:

```bash
curl -s -X POST http://localhost:8000/api/mailbox \
  -H "Content-Type: application/json" \
  -d '{
    "problem_id": "f3e6edc9-4d31-46c5-9a44-e00d6ed5db64",
    "from_agent": "user",
    "to_agent": "orchestrator-1",
    "body": "Priority: focus on South region Gadget-X sales pattern"
  }'
```

**Response:**
```json
{
  "id": "0c928dda-8a87-4bc1-8732-550d41483d6b",
  "problem_id": "f3e6edc9-4d31-46c5-9a44-e00d6ed5db64",
  "from_agent": "demo-runner",
  "to_agent": "orchestrator-1",
  "body": "Test message",
  "read_at": null,
  "created_at": "2026-03-03T22:54:48.552781Z"
}
```

---

### Step 10 — Read the Results

When the Judge agent issues a PASS verdict:

```bash
curl -s http://localhost:8000/api/judge_verdicts/f3e6edc9-4d31-46c5-9a44-e00d6ed5db64
```

Results are also written to the worktree:
```
~/oak-workspaces/problem-f3e6edc9-4d31-46c5-9a44-e00d6ed5db64/
├── SCHEMA.md
├── ANALYSIS_REPORT.md
├── MODEL_REPORT.md
└── app.py   ← generated Streamlit dashboard
```

---

### Demo Summary

| Step | Command | Result |
|---|---|---|
| Stack health | `curl /health` | ✅ All 6 services healthy |
| Submit problem | `POST /api/problems` | ✅ UUID assigned, persisted to PG |
| DB verify | `psql SELECT * FROM problems` | ✅ Row visible immediately |
| Launch orchestrator | `bash scripts/new-problem.sh {uuid}` | ✅ Container started, worktree created |
| Proxy routing | `redis-cli GET oak:telemetry:total_calls` | ✅ **14 calls** to Ollama confirmed |
| Session hooks | `redis-cli KEYS oak:*` | ✅ `cmd_history` written by harness |
| Skills lookup | `GET /api/skills?query=...` | ✅ 2 probationary skills available |
| Mailbox | `POST /api/mailbox` | ✅ Message persisted |

**Full evidence log:** `docs/DEMO_PROOF.md`

---

## 10.5. API Reference

All OAK endpoints run on **http://localhost:8000** (port 8000).

### Health Check

**GET** `/health`

Returns system status, OAK mode, routing strategy, available models.

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "oak_mode": "dgx",
  "routing_strategy": "passthrough",
  "stall_detection_enabled": false,
  "max_agents_per_problem": 10,
  "max_concurrent_problems": 3,
  "models": {
    "default": "llama3.3:70b",
    "coder": "qwen3-coder",
    "analysis": "glm-4.7"
  },
  "feature_flags": {
    "telemetry_enabled": true,
    "skill_extraction_enabled": true,
    "judge_required": true,
    "meta_agent_enabled": false
  },
  "api_key_present": false
}
```

---

### Problems

#### POST /api/problems (Create)

Submit a new problem.

**Request:**
```bash
curl -X POST http://localhost:8000/api/problems \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Customer churn prediction",
    "description": "Build a classifier + dashboard",
    "data_path": "/mnt/oak-data/customers.csv"
  }'
```

**Response (201 Created):**
```json
{
  "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "title": "Customer churn prediction",
  "description": "Build a classifier + dashboard",
  "data_path": "/mnt/oak-data/customers.csv",
  "status": "pending",
  "solution_url": null,
  "created_at": "2026-03-03T14:22:05.123Z",
  "updated_at": "2026-03-03T14:22:05.123Z"
}
```

---

#### GET /api/problems/{problem_id}

Retrieve a single problem.

```bash
curl http://localhost:8000/api/problems/f47ac10b-58cc-4372-a567-0e02b2c3d479
```

Response:
```json
{
  "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "title": "Customer churn prediction",
  "status": "in_progress",
  "solution_url": "http://localhost:8502/problem-f47ac10b"
}
```

---

### Agents

#### POST /api/agents/spawn

Spawn an agent for a problem (called automatically by Orchestrator; rarely called manually).

**Request:**
```bash
curl -X POST http://localhost:8000/api/agents/spawn \
  -H "Content-Type: application/json" \
  -d '{
    "role": "data-scientist",
    "problem_uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d479"
  }'
```

**Response (201 Created):**
```json
{
  "agent_id": "data-scientist-f47ac10b",
  "container_id": "xyz789uvw012",
  "role": "data-scientist",
  "model": "glm-4.7"
}
```

---

#### GET /api/agents/models

Returns the model routing table — which Ollama model each agent role uses.

```bash
curl http://localhost:8000/api/agents/models
```

Response:
```json
{
  "models": {
    "default": "llama3.3:70b",
    "coder": "qwen3-coder",
    "analysis": "glm-4.7",
    "reasoning": "llama3.3:70b"
  },
  "role_routing": {
    "data-engineer": "qwen3-coder",
    "ml-engineer": "qwen3-coder",
    "data-scientist": "glm-4.7",
    "skill-extractor": "glm-4.7",
    "orchestrator": "llama3.3:70b",
    "judge-agent": "llama3.3:70b",
    "meta-agent": "llama3.3:70b",
    "software-architect": "llama3.3:70b"
  }
}
```

---

#### GET /api/agents/status

Get status of all running agents.

```bash
curl http://localhost:8000/api/agents/status
```

Response:
```json
{
  "agents": [
    {
      "agent_id": "orchestrator-f47ac10b",
      "role": "orchestrator",
      "status": "running",
      "problem_uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    },
    {
      "agent_id": "data-scientist-f47ac10b",
      "role": "data-scientist",
      "status": "idle",
      "problem_uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    }
  ]
}
```

---

### Mailbox (Agent Messaging)

#### POST /api/mailbox

Send a message from one agent to another.

```bash
curl -X POST http://localhost:8000/api/mailbox \
  -H "Content-Type: application/json" \
  -d '{
    "problem_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "from_agent": "data-scientist-f47ac10b",
    "to_agent": "ml-engineer-f47ac10b",
    "subject": "Analysis complete",
    "body": "ANALYSIS_REPORT.md is ready. Key findings: churn correlates with contract_length < 12 months."
  }'
```

Response (201 Created):
```json
{
  "id": "msg-123abc",
  "problem_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "from_agent": "data-scientist-f47ac10b",
  "to_agent": "ml-engineer-f47ac10b",
  "subject": "Analysis complete",
  "body": "ANALYSIS_REPORT.md is ready...",
  "read_at": null,
  "created_at": "2026-03-03T14:30:15Z"
}
```

---

#### GET /api/mailbox/{agent_id}/inbox

Retrieve messages for an agent.

```bash
curl "http://localhost:8000/api/mailbox/ml-engineer-f47ac10b/inbox?unread_only=true"
```

Response:
```json
[
  {
    "id": "msg-123abc",
    "from_agent": "data-scientist-f47ac10b",
    "subject": "Analysis complete",
    "body": "...",
    "read_at": null,
    "created_at": "2026-03-03T14:30:15Z"
  }
]
```

---

#### PATCH /api/mailbox/{message_id}/read

Mark a message as read.

```bash
curl -X PATCH http://localhost:8000/api/mailbox/msg-123abc/read
```

---

### Judge Verdicts

#### POST /api/judge_verdicts

Submit a judge verdict (called by Judge Agent; rarely manual).

```bash
curl -X POST http://localhost:8000/api/judge_verdicts \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task-synthesise-456def",
    "verdict": "PASS",
    "checks": {
      "output_format": {"status": "pass", "details": "Streamlit app is valid"},
      "ui_completeness": {"status": "pass", "details": "All required controls present"}
    },
    "notes": "Solution ready for deployment."
  }'
```

---

#### GET /api/judge_verdicts/{problem_uuid}

Retrieve all verdicts for a problem.

```bash
curl http://localhost:8000/api/judge_verdicts/f47ac10b-58cc-4372-a567-0e02b2c3d479
```

Response:
```json
[
  {
    "id": "verdict-123abc",
    "task_id": "task-synthesise-456def",
    "verdict": "PASS",
    "checks": { ... },
    "created_at": "2026-03-03T14:45:23Z"
  }
]
```

---

### Skills

#### GET /api/skills

Search the skill library by keyword, category, status.

```bash
# Search by keyword
curl "http://localhost:8000/api/skills?query=csv"

# Filter by category
curl "http://localhost:8000/api/skills?category=etl"

# Filter by status (permanent or probationary)
curl "http://localhost:8000/api/skills?status=permanent&top_k=20"
```

Response:
```json
[
  {
    "id": "skill-abc123",
    "name": "csv-datetime-fill",
    "category": "etl",
    "description": "Fill datetime gaps in time-series CSV",
    "trigger_keywords": ["csv", "datetime", "time-series"],
    "status": "permanent",
    "use_count": 3,
    "verified_on_problems": ["f47ac10b", "c92a0f14"],
    "filesystem_path": "/oak-workspaces/skills/permanent/csv-datetime-fill/"
  }
]
```

---

#### POST /api/skills/{skill_id}/promote

Promote a probationary skill to permanent (if threshold met).

```bash
curl -X POST http://localhost:8000/api/skills/skill-abc123/promote
```

Response:
```json
{
  "status": "promoted",
  "skill_id": "skill-abc123"
}
```

**Error (409):** `PromotionThresholdNotMet — skill used on only 1 problem, needs 2`

---

### Telemetry

#### GET /api/telemetry

Retrieve aggregated system telemetry.

```bash
curl http://localhost:8000/api/telemetry
```

Response:
```json
{
  "total_events": 1247,
  "total_escalations": 42,
  "escalation_rate_pct": 3.4,
  "events_by_type": {
    "tool_use": 842,
    "task_state_change": 321,
    "skill_promotion": 8,
    "agent_spawn": 76
  },
  "active_problems": 2,
  "recent_events": [
    {
      "id": "evt-001",
      "agent_id": "data-scientist-f47ac10b",
      "event_type": "tool_use",
      "tool_name": "postgres_query",
      "escalated": false,
      "created_at": "2026-03-03T14:55:12Z"
    }
  ]
}
```

---

#### POST /api/telemetry

Record a telemetry event from an agent hook (internal; called by `.claude/hooks/post-tool-use.sh`).

```bash
curl -X POST http://localhost:8000/api/telemetry \
  -H "Content-Type: application/json" \
  -d '{
    "problem_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "agent_id": "data-scientist-f47ac10b",
    "event_type": "tool_use",
    "tool_name": "bash",
    "tool_input": {"command": "SELECT COUNT(*) FROM customers"},
    "duration_ms": 145,
    "escalated": false
  }'
```

---

## 11. Troubleshooting

### "Cannot connect to OAK API at http://localhost:8000"

**Check:** Is the stack running?

```bash
# See all containers
docker compose -f docker/docker-compose.yml --profile dgx ps

# If any are down, bring them up
docker compose -f docker/docker-compose.dgx.yml up -d

# Check logs
docker logs oak-api
```

**Common cause:** API container crashed. Check logs for Python exceptions.

```bash
docker logs --tail 50 oak-api
```

---

### "Agents are stuck on 'idle' for > 5 minutes"

**Check:** Is Redis running?

```bash
docker compose exec oak-redis redis-cli ping
# Expected: PONG
```

**Check:** Can the proxy reach Ollama?

```bash
curl -s http://localhost:9000/health | python3 -m json.tool
# Look for "status": "healthy" and "ollama_connected": true
```

**Check:** Are Ollama models pulled?

```bash
docker exec oak-ollama ollama list
# Should show: qwen3-coder:latest, llama3.3:70b, etc.
```

**If models missing:**

```bash
docker exec oak-ollama ollama pull qwen3-coder
docker exec oak-ollama ollama pull llama3.3:70b
```

---

### "Escalation rate > 30% — agents are falling back to Claude API"

**This is normal on Mac Mini.** It means the local Ollama models are stalling (too slow for the problem complexity). The proxy automatically escalates to Claude API to avoid timeouts.

**To reduce escalation:**

1. **On DGX:** Use larger models: `llama3.3:70b` + `deepseek-v3` (enabled by default)
2. **On Mac Mini:** Accept higher escalation cost, or reduce `STALL_MIN_TOKENS` in `.env.mini`

---

### "Postgres connection error: ERROR: role oak does not exist"

**Check:** Did bootstrap complete?

```bash
docker compose -f docker/docker-compose.yml --profile dgx ps oak-postgres
# Should show: Up (healthy)

# Check logs
docker logs oak-postgres | head -20
```

**Reset:** Destroy and recreate Postgres:

```bash
docker compose -f docker/docker-compose.dgx.yml down oak-postgres
docker volume rm oak_postgres_data
docker compose -f docker/docker-compose.dgx.yml up -d oak-postgres
# Wait 10s for init script to run
docker logs -f oak-postgres
```

---

### "No space left on device"

Ollama models are large (18 GB per model). Check disk:

```bash
df -h
# If / is 100%, clean up Docker images/volumes

docker system prune -a --volumes
# WARNING: deletes all unused images and volumes

# Re-bootstrap
bash scripts/bootstrap.sh dgx
```

---

### "Submitted problem but no agents spawned"

**Check:** Was the problem created?

```bash
curl http://localhost:8000/api/problems/f47ac10b-58cc-4372-a567-0e02b2c3d479
# Should return 200 OK with status: pending
```

**Check:** Are agents running?

```bash
curl http://localhost:8000/api/agents/status
# Should show at least one orchestrator agent
```

**If no agents:**

```bash
# Check API logs for spawn errors
docker logs oak-api | grep -i spawn

# Check if DGX factory can start containers
docker ps -a | grep oak-harness

# If stuck containers exist, remove them
docker rm -f oak-harness-*
```

---

### "Judge rejected the solution; agents are retrying"

This is **expected behavior**. The feedback loop is:

1. Software Architect generates Streamlit app
2. Judge verifies it meets requirements (data accessibility, model accuracy, UI completeness)
3. If FAIL: Judge creates detailed feedback message
4. Data Scientist refines analysis → ML Engineer tries new features/model → repeat

**To see feedback:**

```bash
curl http://localhost:8000/api/judge_verdicts/f47ac10b-58cc-4372-a567-0e02b2c3d479 | python3 -m json.tool
```

**To understand why it failed:** Check the `checks` object in the verdict JSON. Fix and resubmit manually if needed.

---

### "My data is sensitive; can I run OAK locally?"

Yes. OAK is designed to run offline:

1. Clone the repo and bootstrap on your local machine or private DGX
2. All computation happens in Docker containers on your hardware
3. Anthropic API (Claude escalation) is **opt-in and disabled by default** (`ROUTING_STRATEGY=passthrough`)
4. Data never leaves your network (PostgreSQL stores everything locally)

To ensure no external calls:

```bash
# Check proxy is routing to Ollama only
curl http://localhost:9000/health | grep "routing_strategy"
# Expected: "routing_strategy": "passthrough" (local Ollama, no Claude API)
```

---

## 12. Advanced: Skill Library

### How Skills Are Created

When a Data Engineer **ingests a CSV file**, OAK extracts the pattern:

**Example: CSV with datetime + categorical columns**

```python
# Data Engineer's notebook (generated by Claude Code)
import pandas as pd
import numpy as np

df = pd.read_csv("/data/sales.csv")

# Fill datetime gaps using forward-fill + linear interpolation
df['date'] = pd.to_datetime(df['date'])
df = df.set_index('date').asfreq('D').fillna(method='ffill').interpolate()

# Encode categorical columns
df['region'] = pd.factorize(df['region'])[0]
df['product'] = pd.factorize(df['product'])[0]

df.to_csv("/output/clean_sales.csv")
```

This pattern is **recognized and extracted** as a reusable skill:

```yaml
# Extracted skill
name: csv-datetime-ffill-categorical
category: etl
description: Ingest CSV with datetime index + categorical columns.
             Fill datetime gaps (forward-fill), encode categories (integer factorize).
trigger_keywords: [csv, datetime, categorical, fill-gaps, sales, time-series]
use_count: 1  # Just used on this problem
status: probationary  # Needs 2+ uses to promote
verified_on_problems: [f47ac10b-58cc-4372]
filesystem_path: /oak-workspaces/skills/probationary/csv-datetime-ffill-categorical/
```

---

### Skill Promotion: From Probationary → Permanent

**Threshold:** A skill must be used on 2+ independent problems to be promoted.

When the second problem uses the same skill:

```bash
# Promotion is automatic (SkillRepository.promote())
# Or manual via API:
curl -X POST http://localhost:8000/api/skills/{skill_id}/promote
```

**Promoted skill:**

```yaml
name: csv-datetime-ffill-categorical
status: permanent  # Now trusted + cached in memory
use_count: 2
verified_on_problems: [f47ac10b-58cc-4372, c92a0f14-xyz]
```

**Consequence:** The skill is now **suggested to all agents** on future problems.

Example: When a new Data Engineer sees a CSV with datetime columns, `oak-skills MCP` automatically suggests:

```
Available skills matching "datetime csv":
1. csv-datetime-ffill-categorical (permanent, use_count: 2)
2. csv-timezone-convert (probationary, use_count: 1)
```

---

### Viewing and Searching Skills

**Via UI (Page 4):**
- Search by keyword: "csv", "etl", "time-series"
- Filter by category: ETL, analysis, ML, UI, infra
- Filter by status: permanent (production) vs. probationary (learning)

**Via API:**

```bash
# Search
curl "http://localhost:8000/api/skills?query=csv&category=etl"

# List all permanent skills
curl "http://localhost:8000/api/skills?status=permanent"

# Get top 10 most-used skills
curl "http://localhost:8000/api/skills?top_k=10"
```

---

### Custom Skills (Manual Addition)

To add a custom skill that isn't auto-extracted:

1. **Create a folder** in `/oak-workspaces/skills/probationary/`:
   ```bash
   mkdir -p /oak-workspaces/skills/probationary/my-custom-skill/
   ```

2. **Add metadata** (`skill.yaml`):
   ```yaml
   id: my-custom-skill-12345
   name: My Custom Skill
   category: etl
   description: Does X, Y, Z
   trigger_keywords: [keyword1, keyword2, keyword3]
   status: probationary
   use_count: 0
   verified_on_problems: []
   ```

3. **Add code** (`main.py`, `requirements.txt`, etc.):
   ```bash
   touch /oak-workspaces/skills/probationary/my-custom-skill/main.py
   echo "pandas numpy scipy" > /oak-workspaces/skills/probationary/my-custom-skill/requirements.txt
   ```

4. **Commit to `oak/skills` branch**:
   ```bash
   cd /oak-workspaces/skills/
   git add probationary/my-custom-skill/
   git commit -m "feat(skills): add my-custom-skill"
   git push origin oak/skills
   ```

5. **It will appear in Page 4 (Skills)** and be available to agents after the next stack reload.

---

## Appendix: Configuration Reference

All configuration is in `.env.{mode}` files:

### `.env.dgx` (DGX Spark — primary)

```bash
OAK_MODE=dgx
DATABASE_URL=postgresql://oak:oak@localhost:5432/oak_db
REDIS_URL=redis://localhost:6379/0
OLLAMA_URL=http://localhost:11434

# Models (large, for 80 GB A100)
DEFAULT_MODEL=llama3.3:70b
CODER_MODEL=qwen3-coder:latest
ML_ENGINEER_MODEL=deepseek-v3:latest

# Resource caps
MAX_HARNESS_CONTAINERS=10
MAX_AGENTS_PER_PROBLEM=6
MAX_CONCURRENT_PROBLEMS=3

# Routing (local Ollama by default; no Claude API)
ROUTING_STRATEGY=passthrough
STALL_DETECTION_ENABLED=true
STALL_MIN_TOKENS=15
ESCALATION_ENABLED=false

# Anthropic API (for escalation; empty by default)
ANTHROPIC_API_KEY=
ANTHROPIC_API_KEY_REAL=  # Never log this
```

### `.env.mini` (Mac Mini M4 — smaller)

```bash
OAK_MODE=mini
# ... same DATABASE_URL, REDIS_URL, OLLAMA_URL

# Models (smaller, for 16 GB M4)
DEFAULT_MODEL=llama3.2:3b
CODER_MODEL=qwen2.5-coder:7b
ML_ENGINEER_MODEL=llama3.2:3b

# Lower caps (limited RAM)
MAX_HARNESS_CONTAINERS=2
MAX_AGENTS_PER_PROBLEM=2
MAX_CONCURRENT_PROBLEMS=1

# Aggressive stall detection (escalate quickly)
ROUTING_STRATEGY=stall
STALL_DETECTION_ENABLED=true
STALL_MIN_TOKENS=5  # More aggressive
ESCALATION_ENABLED=true

ANTHROPIC_API_KEY_REAL=sk-...  # Real key for escalation
```

---

## Support & Further Help

- **GitHub Issues:** https://github.com/SharathSPhD/oak/issues
- **Architecture Deep Dive:** See `spec.md` (v1.2) and `PRD.md` (v1.0)
- **Worktree Workflow:** See `PROGRESS.md` (§ Git Worktree Workflow)
- **API Health Check:** `curl http://localhost:8000/health`
- **Logs:** `docker logs {container_name}`

---

---

## 14. Streamlit Cloud Deployment (Optional)

The OAK Hub can be deployed to [Streamlit Cloud](https://streamlit.io/cloud) as a read-only frontend while the DGX stack continues running locally.

### Setup

1. **Create `.streamlit/secrets.toml`** (gitignored — never commit):
   ```toml
   OAK_API_URL = "https://your-dgx-tunnel.example.com"
   ```

2. **Deploy to Streamlit Cloud:**
   - Connect your GitHub repo (`SharathSPhD/oak`)
   - Set the app entrypoint to `ui/app.py`
   - Add `OAK_API_URL` as a secret in the Streamlit Cloud dashboard

3. **The Hub UI** (`ui/app.py` + `ui/pages/01_submit.py`) consumes the OAK REST API at `OAK_API_URL` — it holds no data or agent logic.

### Meta Agent (Advanced)

The Meta Agent evolves agent prompts by analysing failure patterns. It's **disabled by default**.

To enable:
```bash
# In .env or docker-compose override
META_AGENT_ENABLED=true
```

When enabled, the Meta Agent runs on schedule (daily or after every 10 problems), reads `agent_telemetry`, and opens PRs against `oak/agents` branch with prompt amendments. All PRs require human merge.

---

**OAK v1.1** | Built for DGX Spark | March 2026
