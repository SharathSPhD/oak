#!/bin/bash
# OAK Full-stack bootstrap for DGX Spark
# Usage: bash /any/path/scripts/bootstrap.sh [dgx|mini|cloud]
# Self-contained: resolves its own location — works from any CWD.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OAK_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

MODE="${1:-dgx}"
export OAK_MODE="$MODE"
COMPOSE_FILE="${OAK_ROOT}/docker/docker-compose.${MODE}.yml"

echo "[bootstrap] OAK root : $OAK_ROOT"
echo "[bootstrap] Mode     : $MODE"
echo "[bootstrap] Compose  : $COMPOSE_FILE"

# --project-directory makes all relative paths in compose files resolve from OAK_ROOT
DC="docker compose --project-directory ${OAK_ROOT} -f ${COMPOSE_FILE}"

# ── Build images ──────────────────────────────────────────────────────────────
echo "[bootstrap] Building oak/api-proxy ..."
docker build -t oak/api-proxy:latest "${OAK_ROOT}/oak_mcp/oak-api-proxy/"

echo "[bootstrap] Building oak/harness ..."
docker build -t oak/harness:latest "${OAK_ROOT}/docker/claude-harness/"

echo "[bootstrap] Building oak/api ..."
docker build -t oak/api:latest -f "${OAK_ROOT}/docker/api/Dockerfile" "${OAK_ROOT}"

echo "[bootstrap] Building oak/ui ..."
docker build -t oak/ui:latest "${OAK_ROOT}/ui/"

# ── Start infrastructure (Postgres + Redis need to be healthy before API) ─────
echo "[bootstrap] Starting oak-postgres and oak-redis ..."
$DC up -d oak-postgres oak-redis

echo "[bootstrap] Waiting for Postgres and Redis to be healthy ..."
for i in $(seq 1 30); do
    PG_HEALTHY=$($DC ps oak-postgres 2>/dev/null | grep -c "healthy" || true)
    RD_HEALTHY=$($DC ps oak-redis   2>/dev/null | grep -c "healthy" || true)
    if [ "$PG_HEALTHY" -ge 1 ] && [ "$RD_HEALTHY" -ge 1 ]; then
        echo "[bootstrap] Infrastructure healthy."
        break
    fi
    sleep 2
done

# ── Start core services ───────────────────────────────────────────────────────
echo "[bootstrap] Starting oak-api-proxy and oak-api ..."
$DC up -d oak-api-proxy oak-api

# ── DGX-specific: Ollama + models ─────────────────────────────────────────────
if [ "$MODE" = "dgx" ]; then
    echo "[bootstrap] Starting oak-ollama (GPU) ..."
    $DC up -d oak-ollama

    echo "[bootstrap] Waiting for Ollama to start ..."
    sleep 10

    echo "[bootstrap] Pulling primary models (this may take a while on first run) ..."
    docker exec oak-ollama ollama pull qwen3-coder || echo "[warn] qwen3-coder pull failed — retry: docker exec oak-ollama ollama pull qwen3-coder"
    docker exec oak-ollama ollama pull glm-4.7    || echo "[warn] glm-4.7 pull failed"
fi

# ── UI ────────────────────────────────────────────────────────────────────────
echo "[bootstrap] Starting oak-ui ..."
$DC up -d oak-ui

# ── Seed skills DB ────────────────────────────────────────────────────────────
echo "[bootstrap] Seeding skill library ..."
sleep 5
PG_CONTAINER=$($DC ps -q oak-postgres 2>/dev/null || echo "")
if [ -n "$PG_CONTAINER" ]; then
    docker exec -i "$PG_CONTAINER" \
        psql -U oak -d oak < "${OAK_ROOT}/scripts/seed_skills.sql" 2>/dev/null \
        || echo "[warn] Skill seed skipped (will auto-apply on next start)"
fi

# ── Status ────────────────────────────────────────────────────────────────────
echo ""
echo "[bootstrap] Stack launched. Verify with:"
echo "  $DC ps"
echo "  curl http://localhost:8000/health"
echo "  curl http://localhost:9000/health"
echo "  curl http://localhost:11434/api/tags"
echo "  curl http://localhost:8501/_stcore/health"
