---
description: Run a self-audit of the OAK system — analyze telemetry, skill gaps, failure patterns, and produce a structured gap report.
---

You are the OAK Cortex introspection engine. Run a full self-audit:

1. Fetch system telemetry from the OAK API:
   - GET http://oak-api:8000/api/telemetry (recent agent events)
   - GET http://oak-api:8000/api/problems (all problems, check pass/fail rates)
   - GET http://oak-api:8000/api/skills (permanent vs probationary counts)
   - GET http://oak-api:8000/health (system health)

2. Read `manifest_domains.json` from the repo root to identify target domains.

3. For each domain, compare permanent skill count against the floor threshold.

4. Analyze recent failures:
   - Group by failure type (code_failure, data_failure, model_failure, decomposition_failure)
   - Identify recurring patterns across failures
   - Note which agent roles fail most often

5. Produce a structured JSON report with:
   ```json
   {
     "timestamp": "ISO-8601",
     "skill_gaps": [{"domain": "...", "gap_score": 0.8, "permanent": 1, "floor": 3}],
     "failure_patterns": [{"type": "...", "count": N, "roles": [...]}],
     "model_utilization": {"model_name": {"tasks": N, "avg_score": 0.7}},
     "recommendations": ["...", "..."]
   }
   ```

6. Write the report to `/workspaces/builder/audit_report.json`.

Return the report summary to the user.
