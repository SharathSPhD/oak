#!/usr/bin/env bash
# OAK Watchdog — ensures builder (Cortex) container is always running and handles hot-swap.
# Minimal, never-self-modifying. Polls builder state, restarts if down, processes REPLACE signals.

set -euo pipefail

BUILDER_CONTAINER="${BUILDER_CONTAINER:-docker_oak-builder_1}"
OAK_ROOT="${OAK_ROOT:-/home/sharaths/projects/oak}"
COMPOSE_FILE="${OAK_ROOT}/docker/docker-compose.yml"
SIGNALS_DIR="/watchdog/signals"
HEARTBEAT_FILE="/watchdog/watchdog_heartbeat.json"
HEARTBEAT_URL="${OAK_BUILDER_HEARTBEAT_URL:-http://localhost:8080/health}"
HEALTH_TIMEOUT=60
HEALTH_POLL_INTERVAL=2
POLL_INTERVAL=5

log() { echo "[watchdog $(date +%H:%M:%S)] $*"; }

# Graceful shutdown on SIGTERM
shutdown=0
trap 'shutdown=1; log "SIGTERM received, shutting down gracefully"' SIGTERM

ts() { date +%Y-%m-%dT%H:%M:%S; }

write_heartbeat() {
  local status="$1"
  local extra="${2:-{}}"
  echo "{\"ts\":\"$(ts)\",\"status\":\"${status}\",\"builder\":\"${BUILDER_CONTAINER}\"${extra:+,$extra}}" > "${HEARTBEAT_FILE}" 2>/dev/null || true
}

builder_running() {
  docker inspect -f '{{.State.Running}}' "${BUILDER_CONTAINER}" 2>/dev/null | grep -q true
}

replace_signal_pending() {
  [[ -f "${SIGNALS_DIR}/replace.json" ]]
}

do_restart_builder() {
  log "Restarting builder via docker compose"
  (cd "${OAK_ROOT}" && docker compose -f "${COMPOSE_FILE}" up -d oak-builder) || {
    log "ERROR: Failed to restart builder"
    write_heartbeat "restart_failed" "\"error\":\"compose up failed\""
    return 1
  }
}

process_replace_signal() {
  local signal_file="${SIGNALS_DIR}/replace.json"
  local new_image handover_state

  new_image=$(jq -r '.new_image // empty' "${signal_file}" 2>/dev/null)
  handover_state=$(jq -c '.handover_state // {}' "${signal_file}" 2>/dev/null)

  if [[ -z "${new_image}" ]]; then
    log "ERROR: replace.json missing new_image"
    echo "{\"error\":\"missing new_image\",\"ts\":\"$(ts)\"}" > "${SIGNALS_DIR}/error.json"
    rm -f "${signal_file}"
    return 1
  fi

  log "Processing REPLACE: new_image=${new_image}"

  # Build env vars from current builder
  local env_args=()
  local env_json
  env_json=$(docker inspect -f '{{json .Config.Env}}' "${BUILDER_CONTAINER}" 2>/dev/null) || env_json="[]"
  while IFS= read -r line; do
    [[ -n "$line" ]] && env_args+=(-e "$line")
  done < <(echo "${env_json}" | jq -r '.[]?' 2>/dev/null)

  # Get network from current builder
  local network
  network=$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}' "${BUILDER_CONTAINER}" 2>/dev/null) || network="oak-net"

  # Get mounts from current builder (tab-separated to handle colons in paths)
  local mounts_args=()
  local mount_src mount_dst
  while IFS=$'\t' read -r mount_src mount_dst; do
    [[ -n "$mount_src" && -n "$mount_dst" ]] && mounts_args+=(-v "${mount_src}:${mount_dst}")
  done < <(docker inspect -f '{{range .Mounts}}{{.Source}}{{"\t"}}{{.Destination}}{{"\n"}}{{end}}' "${BUILDER_CONTAINER}" 2>/dev/null)

  # Run new container
  if ! docker run -d --name oak-builder-next \
    --network "${network}" \
    "${env_args[@]}" \
    "${mounts_args[@]}" \
    "${new_image}"; then
    log "ERROR: Failed to run new container"
    echo "{\"error\":\"docker run failed\",\"image\":\"${new_image}\",\"ts\":\"$(ts)\"}" > "${SIGNALS_DIR}/error.json"
    rm -f "${signal_file}"
    return 1
  fi

  # Health-check new container
  local elapsed=0
  local healthy=0
  while [[ $elapsed -lt $HEALTH_TIMEOUT ]]; do
    if docker exec oak-builder-next curl -sf --max-time 5 "${HEARTBEAT_URL}" >/dev/null 2>&1; then
      healthy=1
      break
    fi
    sleep "${HEALTH_POLL_INTERVAL}"
    elapsed=$((elapsed + HEALTH_POLL_INTERVAL))
  done

  if [[ $healthy -eq 0 ]]; then
    log "ERROR: New container unhealthy after ${HEALTH_TIMEOUT}s"
    docker stop oak-builder-next 2>/dev/null || true
    docker rm oak-builder-next 2>/dev/null || true
    echo "{\"error\":\"health check failed\",\"image\":\"${new_image}\",\"ts\":\"$(ts)\"}" > "${SIGNALS_DIR}/error.json"
    rm -f "${signal_file}"
    return 1
  fi

  # Swap: stop old, remove, rename new
  log "Swapping: stopping old builder"
  docker stop "${BUILDER_CONTAINER}" 2>/dev/null || true
  docker rm "${BUILDER_CONTAINER}" 2>/dev/null || true
  docker rename oak-builder-next "${BUILDER_CONTAINER}" 2>/dev/null || true

  jq -n --argjson hs "${handover_state}" --arg ts "$(ts)" --arg img "${new_image}" '{handover_state:$hs,ts:$ts,new_image:$img}' > "${SIGNALS_DIR}/handover.json"
  rm -f "${signal_file}"
  log "REPLACE complete: ${new_image} is now ${BUILDER_CONTAINER}"
}

main_loop() {
  while [[ $shutdown -eq 0 ]]; do
    if replace_signal_pending; then
      process_replace_signal || true
    elif ! builder_running; then
      do_restart_builder || true
    fi
    write_heartbeat "ok"
    sleep "${POLL_INTERVAL}"
  done
  log "Watchdog stopped"
}

write_heartbeat "starting"
main_loop
