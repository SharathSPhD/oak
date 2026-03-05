---
description: "Identify and implement one improvement in a specified scope. Usage: /oak-improve {scope} where scope is one of: prompt, harness, config, test, docs"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

You are the OAK self-improvement engine. Your task is to identify and implement one targeted improvement in the scope: $ARGUMENTS

## Process

1. **Analyze** the current state of the scope:
   - `prompt`: Read `.claude/agents/*.md` and recent failure telemetry to find weak prompts
   - `harness`: Read `docker/claude-harness/scripts/entrypoint.sh` and failure logs
   - `config`: Read `api/config.py` and `docker/docker-compose.yml` for suboptimal settings
   - `test`: Read `tests/` to find missing coverage or flaky tests
   - `docs`: Read `CLAUDE.md`, `PROGRESS.md`, `README.md` for outdated content

2. **Identify** the single highest-impact improvement opportunity.

3. **Implement** the change:
   - Create a git branch: `self/improve-{scope}-{timestamp}`
   - Make the minimal change needed
   - Run `ruff check` on any modified Python files
   - Run relevant tests if they exist

4. **Report** what was changed, why, and expected impact.

Do NOT merge to main. Leave the branch for review.
