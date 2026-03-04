# OAK Demo Proof 3 — Post-Critique5 Fixes

**Date:** 2026-03-04  
**Commit:** Post oak-critique5 remediation  

## Changes Implemented (from oak-critique5.md)

| Gap | Fix | Status |
|---|---|---|
| 1a. episodic.py `NotImplementedError` stubs | `PostgresEpisodicMemoryRepository` now delegates to working `PostgreSQLEpisodicRepository` | DONE |
| 1b. Skill retrieval not in orchestrator | Step 1b queries `GET /api/skills?query=...` and injects into decomposition prompt | DONE |
| 2a. Judge spawned without task_id | Judge task created via `POST /api/tasks` before spawn, task_id passed | DONE |
| 2b. Skill-extractor same gap | Skill-extractor task created and tracked identically | DONE |
| 2c. `assembling` status never set | Step 0 now calls `patch_problem "assembling"` before decomposition | DONE |
| 3a. Embedding dim 1536 vs 768 mismatch | `schema.sql` changed to `vector(768)`, `EMBED_MODEL`/`EMBED_DIM` added to `OAKSettings` | DONE |
| 3b. Duplicate episodic implementations | `episodic.py` consolidated to delegate to `episodic_repository.py` | DONE |
| 3c. Worktree cleanup on delete | `delete_problem` now runs `git worktree remove`, `git branch -D`, `shutil.rmtree` | DONE |
| 3d. MAX_CONCURRENT_PROBLEMS not enforced | `create_problem` now checks active count, returns 429 if exceeded | DONE |
| 4a. WebSocket log streaming | Already existed — no changes needed | N/A |
| 4b. Meta-agent proposals write-only | `POST /api/meta/apply-proposals` and `GET /api/meta/proposals` endpoints added | DONE |
| Judge verdict SQL error | Fixed `:checks::jsonb` → `CAST(:checks AS jsonb)` in judge router | DONE |
| Docker network mismatch | `.env` updated from `oak_oak-net` to `docker_oak-net`, compose default fixed | DONE |

## Demo Run: "Sales Trend Forecast"

- **Problem ID:** `ca2dcb14-57b6-42d8-9c33-3cdc7d88fb69`
- **Pipeline Duration:** ~8 minutes
- **Status:** `complete` (PASS verdict)

### Pipeline Steps Verified

1. **Step 0**: `assembling` status set before decomposition
2. **Step 1b**: Skill library queried (empty — first run, as expected)
3. **Step 2**: Ollama API decomposition → 5 tasks
4. **Step 3**: 5 specialist agents spawned (data-engineer, 3x data-scientist, ml-engineer)
5. **Step 4**: Polling until all 5 complete (0 failures)
6. **Step 5**: Judge spawned with tracked task_id `197e4135-...`
7. **Step 6**: Skill extractor spawned with tracked task_id `10ac5cd5-...`
8. **Step 7**: Problem marked `complete`

### Judge Verdict

```json
{
    "verdict": "pass",
    "checks": {
        "problem_addressed": true,
        "code_valid": true,
        "artifacts_present": true,
        "analysis_evident": true
    }
}
```

Verdict stored in `judge_verdicts` table (confirmed via psql query).

### Unit Tests

All 132 unit tests pass (`pytest tests/unit/ -v`).

### Linting

`ruff check api/ memory/` — all checks passed.

### Screenshots

- `demo_screenshots_v3/gallery.png` — Problem gallery
- `demo_screenshots_v3/problem_detail.png` — Problem detail with tasks
- `demo_screenshots_v3/health.png` — Health dashboard
