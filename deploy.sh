#!/bin/bash
# Rolling deployment script for TripBuddy
# Usage: ./deploy.sh <backend-image> <frontend-image> <prometheus-image> <grafana-image>
# All image arguments are optional; falls back to the BACKEND_IMAGE / FRONTEND_IMAGE /
# PROMETHEUS_IMAGE / GRAFANA_IMAGE environment variables already set in the caller.

set -euo pipefail

BACKEND_IMAGE="${1:-${BACKEND_IMAGE:-tripbuddy-backend:latest}}"
FRONTEND_IMAGE="${2:-${FRONTEND_IMAGE:-tripbuddy-frontend:latest}}"
PROMETHEUS_IMAGE="${3:-${PROMETHEUS_IMAGE:-tripbuddy-prometheus:latest}}"
GRAFANA_IMAGE="${4:-${GRAFANA_IMAGE:-tripbuddy-grafana:latest}}"

ENV_FILE="${ENV_FILE:-.env.prod}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

# How long (seconds) to wait for health checks before declaring failure
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-120}"

export BACKEND_IMAGE FRONTEND_IMAGE PROMETHEUS_IMAGE GRAFANA_IMAGE

COMPOSE_CMD="docker compose --env-file $ENV_FILE -f $COMPOSE_FILE"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

log()  { echo "[deploy] $*"; }
fail() { echo "[deploy] ERROR: $*" >&2; exit 1; }

wait_healthy() {
    local service="$1"
    local deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
    log "Waiting for '$service' to become healthy (timeout ${HEALTH_TIMEOUT}s)..."
    while true; do
        local status
        status=$(docker inspect --format '{{.State.Health.Status}}' \
            "$(${COMPOSE_CMD} ps -q "$service" 2>/dev/null | head -1)" 2>/dev/null || echo "none")
        if [ "$status" = "healthy" ]; then
            log "'$service' is healthy."
            return 0
        fi
        if [ "$(date +%s)" -ge "$deadline" ]; then
            log "'$service' did not become healthy within ${HEALTH_TIMEOUT}s (last status: $status)."
            return 1
        fi
        sleep 5
    done
}

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

if [ ! -f "$ENV_FILE" ]; then
    fail "Environment file not found: $ENV_FILE"
fi

log "Starting rolling deployment"
log "  backend   : $BACKEND_IMAGE"
log "  frontend  : $FRONTEND_IMAGE"
log "  prometheus: $PROMETHEUS_IMAGE"
log "  grafana   : $GRAFANA_IMAGE"
log "  env file  : $ENV_FILE"
log "  compose   : $COMPOSE_FILE"

# ---------------------------------------------------------------------------
# Step 1: Rolling update for backend and frontend (health-check gated)
# ---------------------------------------------------------------------------
# Each is updated one at a time; if the health check doesn't pass within
# HEALTH_TIMEOUT seconds the whole stack is rolled back to :latest images.
for service in backend frontend; do
    log "---------- Rolling update: $service ----------"
    ${COMPOSE_CMD} up -d --no-deps --pull missing "$service"

    if ! wait_healthy "$service"; then
        log "Health check failed for '$service'. Rolling back entire stack..."
        ${COMPOSE_CMD} down || true

        log "Attempting rollback to latest-tagged images..."
        BACKEND_IMAGE="tripbuddy-backend:latest" \
        FRONTEND_IMAGE="tripbuddy-frontend:latest" \
        PROMETHEUS_IMAGE="tripbuddy-prometheus:latest" \
        GRAFANA_IMAGE="tripbuddy-grafana:latest" \
        ${COMPOSE_CMD} up -d || true

        fail "Deployment aborted after failed health check on '$service'."
    fi
done

# ---------------------------------------------------------------------------
# Step 2: Simple update for monitoring services (no health-check gating)
# ---------------------------------------------------------------------------
for service in prometheus grafana; do
    log "---------- Updating $service ----------"
    ${COMPOSE_CMD} up -d --no-deps --pull missing "$service"
    log "'$service' updated."
done

# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------
log "=========================================="
log "Deployment successful!"
log "Build images deployed:"
log "  backend   : $BACKEND_IMAGE"
log "  frontend  : $FRONTEND_IMAGE"
log "  prometheus: $PROMETHEUS_IMAGE"
log "  grafana   : $GRAFANA_IMAGE"
log ""
log "Running containers:"
${COMPOSE_CMD} ps

log "=========================================="

# Prune dangling images to reclaim disk space
log "Cleaning up dangling images..."
docker image prune -f

log "Done."
