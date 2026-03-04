# OAK React Hub UI — E2E Demo Proof

**Date:** March 4, 2026
**Platform:** DGX Spark (NVIDIA, aarch64)
**OAK Version:** v0.7.0
**UI:** React/Next.js 15 (replaced Streamlit)

---

## Stack Status

| Service            | Container                | Status  |
|--------------------|--------------------------|---------|
| PostgreSQL 16      | oak-oak-postgres-1       | Healthy |
| Redis 7            | oak-oak-redis-1          | Healthy |
| Ollama (GPU)       | oak-oak-ollama-1         | Running |
| FastAPI API        | oak-oak-api-1            | Healthy |
| API Proxy          | oak-oak-api-proxy-1      | Running |
| React UI (Next.js) | oak-oak-ui-1             | Running |
| Self-Healing Daemon| oak-oak-daemon-1         | Running |
| Harness (active)   | oak-harness-*            | Running |

**Total containers:** 8 (including 1 on-demand harness)

---

## Demo Sequence

### 1. Dashboard (`/`)
- System Health: **Healthy** (green indicator)
- Stats: 16 total problems, 1 completed, 0 active agents, 3 models
- Navigation cards: Submit Problem, View Gallery, Telemetry
- Recent problems list with status badges
- **Screenshot:** `demo_screenshots/01_dashboard.png`

### 2. Submit Problem (`/submit`)
- Clean form with title, description, file upload (drag-and-drop)
- Auto-start checkbox enabled by default
- **Screenshot (empty):** `demo_screenshots/02_submit_empty.png`
- Filled with "Wine Quality Prediction" problem
- **Screenshot (filled):** `demo_screenshots/03_submit_filled.png`

### 3. Problem Auto-Created and Started
- Form submitted successfully
- Auto-redirected to problem detail page
- Status: ACTIVE, Container: Up
- Tabs: Tasks (0), Logs, Files (2), Judge Verdicts (0)
- **Screenshot:** `demo_screenshots/04_submit_result.png`

### 4. Gallery (`/gallery`)
- Shows all 17 problems with filter tabs (All, Pending, Active, Complete, Failed)
- Per-problem actions: Start (for pending), Delete (trash icon)
- "Clean Stale" bulk cleanup button at top-right
- "New Problem" button for quick navigation
- **Screenshot:** `demo_screenshots/05_gallery.png`

### 5. Gallery Cleanup
- Clicked "Clean Stale" button
- Response: "Cleaned 0 of 1 stale problems"
- **Screenshot:** `demo_screenshots/06_gallery_cleanup.png`

### 6. Problem Detail — Tabs
- **Tasks tab:** Shows task list (empty for new problem)
  - Screenshot: `demo_screenshots/07_tasks_tab.png`
- **Logs tab:** Live WebSocket stream connected, showing container entrypoint logs
  - Logs show: fetching problem from API, writing PROBLEM.md, generating solution
  - Screenshot: `demo_screenshots/07_logs_tab.png`
- **Files tab:** Shows workspace path and files (PROBLEM.md 462B, solution.py)
  - Screenshot: `demo_screenshots/07_files_tab.png`

### 7. Skill Library (`/skills`)
- Search bar with category and status filters
- Empty state with explanatory message
- **Screenshot:** `demo_screenshots/08_skills.png`

### 8. Telemetry Dashboard (`/telemetry`)
- Metrics cards: Total Events, Escalation Rate (0.0%), Active Problems, System Mode (DGX)
- Events by Type section
- Model Routing: Base models (qwen3-coder, glm-4.7, llama3.3:70b) + Role assignments
- Feature Flags: All 4 enabled (Telemetry, Skill Extraction, Judge, Meta Agent)
- Recent Events section
- **Screenshot:** `demo_screenshots/09_telemetry.png`

### 9. System Settings (`/settings`)
- System Health panel with status details
- Active Agents: Shows 1 running meta-agent (daemon-spawned)
- Configuration Reference table with all environment variables
- **Screenshot:** `demo_screenshots/14_final_settings.png`

---

## Self-Healing Daemon Verification

The `oak-daemon` service successfully:
1. Runs health checks every 60 seconds
2. Detects system idle state (0 active problems, 0 issues)
3. Correctly reads `META_AGENT_ENABLED=true` via `/health` endpoint
4. Spawned meta-agent for self-improvement:
   ```
   META: Triggering meta-agent for self-improvement...
   META: Agent spawned: {"agent_id":"3f0ee7d8-...","role":"meta-agent","model":"llama3.3:70b"}
   ```
5. Respects cooldown period (3600s default)

---

## Bugs Found and Fixed

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| Browser couldn't reach API | `NEXT_PUBLIC_API_URL=http://oak-api:8000` baked at build time, Docker hostname not resolvable from browser | Implemented Next.js rewrites proxy (`/oak-api/*` -> `http://oak-api:8000/*`), changed client to use relative URLs |
| Daemon always showed "META: Disabled via feature flag" | `python3` used for JSON parsing but Alpine container has no Python | Replaced with `jq` for JSON parsing |

---

## Architecture Verified

- **React Hub** (Next.js 15, TanStack Query, Tailwind CSS) serving on port 8501
- **API Proxy Pattern**: Browser -> Next.js `:8501/oak-api/*` -> FastAPI `:8000/*`
- **WebSocket**: Direct connection `ws://host:8000/ws/{problemId}` for live logs
- **Self-Healing Loop**: Daemon -> API health check -> Meta Agent spawn -> Cooldown

---

## Screenshots Index

| # | Page | File |
|---|------|------|
| 01 | Dashboard | `01_dashboard.png` |
| 02 | Submit (empty) | `02_submit_empty.png` |
| 03 | Submit (filled) | `03_submit_filled.png` |
| 04 | Submit Result / Problem Detail | `04_submit_result.png` |
| 05 | Gallery | `05_gallery.png` |
| 06 | Gallery (after cleanup) | `06_gallery_cleanup.png` |
| 07 | Problem Detail - Tasks | `07_tasks_tab.png` |
| 07 | Problem Detail - Logs | `07_logs_tab.png` |
| 07 | Problem Detail - Files | `07_files_tab.png` |
| 08 | Skill Library | `08_skills.png` |
| 09 | Telemetry Dashboard | `09_telemetry.png` |
| 10 | Settings | `10_settings.png` |
| 11 | Dashboard (final) | `11_final_dashboard.png` |
| 14 | Settings (with meta-agent) | `14_final_settings.png` |

**Total: 20 screenshots captured**
