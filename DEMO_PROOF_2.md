# OAK Demo Proof — Full Pipeline Run (March 4, 2026)

## Summary

End-to-end demonstration of the OAK multi-agent pipeline running on DGX Spark with local models.

## Environment

| Component | Details |
|---|---|
| Platform | DGX Spark (OAK_MODE=dgx) |
| Model | qwen3-coder (45GB, 100% GPU) |
| Routing | Passthrough (Ollama via oak-api-proxy) |
| UI | React/Next.js at :8501 |
| API | FastAPI at :8000 |

## Pipeline Execution

### Problem: "Sales Trend Analysis" (90cffddf-4bd5-4575-90a8-6e253a6c56e2)

**Input**: `sales_data.csv` (240 rows, 5 products, 4 regions, 12 months)

#### Step-by-step Pipeline:

1. **Problem Created** — POST `/api/problems` returns UUID, status `pending`
2. **Pipeline Started** — POST `/api/problems/{id}/start` launches `oak-harness` container
3. **PROBLEM.md Written** — Orchestrator writes problem context file
4. **Task Decomposition** — Direct Ollama API call decomposes into 4 tasks:
   - Load and Clean Sales Data (ingest → data-engineer)
   - Compute Monthly Revenue Trends (analyse → data-scientist)
   - Identify Top Products by Volume (analyse → data-scientist)
   - Generate Analysis Report (synthesise → data-scientist)
5. **Specialist Agents Spawned** — 4 containers launched with unique task-based names
6. **Tasks Polled to Completion** — All 4/4 tasks complete within ~60 seconds
7. **Judge Ran** — Produces valid JSON verdict via direct Ollama API
8. **Skill Extractor Ran** — Scans for reusable patterns
9. **Problem Marked Complete** — Status updated to `complete`

### Timing

| Phase | Duration |
|---|---|
| Decomposition (via Ollama API) | ~8 seconds |
| Specialist execution (parallel) | ~60 seconds |
| Judge evaluation | ~15 seconds |
| Total pipeline | ~2 minutes |

## Bugs Found & Fixed

### 1. Claude CLI Agent Loop (Critical)
**Symptom**: `claude --dangerously-skip-permissions -p "..."` hung indefinitely in task decomposition.
**Root Cause**: Local model through Claude Code's agentic mode entered infinite tool-use loops.
**Fix**: Replaced decomposition and judge steps with direct Ollama API calls (urllib → Messages API).
Specialist agents retained Claude CLI with `--max-turns 15` safety limit.

### 2. Container Name Collision (Medium)
**Symptom**: When multiple tasks share the same role (e.g., two `data-scientist` tasks),
the second `spawn-agent` call killed the first container, leaving tasks stuck at "claimed".
**Root Cause**: Container name was `oak-{role}-{problem_id}`, not unique per task.
**Fix**: Changed to `oak-{role}-{task_id[:8]}` for unique naming.

## Screenshots

All screenshots saved in `demo_screenshots/`:
- `demo_01_dashboard.png` — Dashboard with 17 problems, 6 completed, system healthy
- `demo_02_submit.png` — Submit problem form with file upload
- `demo_03_gallery.png` — Gallery showing all problems with status filters
- `demo_04_problem_detail.png` — Problem detail with 4 tasks all Complete
- `demo_05_skills.png` — Skill Library page
- `demo_06_telemetry.png` — Telemetry showing model routing and feature flags
- `demo_07_settings.png` — Settings with system health and configuration reference
- `demo_08_submit_filled.png` — Submit form with data filled
- `demo_09_final_dashboard.png` — Final dashboard state
- `demo_video.webm` — Full video recording of UI walkthrough

## UI Verification

All pages functional:
- [x] Dashboard: System healthy, stats accurate, recent problems listed
- [x] Submit: Form with title, description, file upload, auto-start toggle
- [x] Gallery: Filters (All/Pending/Active/Complete/Failed), Clean Stale button, per-problem delete
- [x] Problem Detail: Status badge, task list, logs tab, files tab, judge verdicts tab
- [x] Skill Library: Skills listing page
- [x] Telemetry: Model routing (role → model assignments), feature flags, event counts
- [x] Settings: System health, active agents, configuration reference table

## API Endpoints Verified

- `GET /health` — System health with models and feature flags
- `POST /api/problems` — Create problem
- `POST /api/problems/{id}/start` — Start pipeline
- `GET /api/problems` — List problems
- `GET /api/problems/{id}` — Problem detail
- `PATCH /api/problems/{id}` — Update status
- `POST /api/problems/{id}/spawn-agent` — Spawn specialist
- `GET /api/tasks?problem_id={id}` — Task listing
- `PATCH /api/tasks/{id}/status` — Update task status
- `POST /api/problems/cleanup` — Clean stale problems
