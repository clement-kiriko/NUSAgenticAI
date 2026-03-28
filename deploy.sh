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

# Blue-green rolling deploy settings
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-tripbuddy}"
BUILD_ID="${BUILD_ID:-$(date +%s)}"
NETWORK_NAME="${COMPOSE_PROJECT_NAME}_default"
BACKEND_ENV_FILE="${BACKEND_ENV_FILE:-TripBuddy/backend/.env.prod}"
GREEN_CONTAINER="backend_green_${BUILD_ID}"

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

# Wait for a bare docker container (not a compose service) to become healthy.
wait_healthy_container() {
    local container="$1"
    local deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
    log "Waiting for container '$container' to become healthy (timeout ${HEALTH_TIMEOUT}s)..."
    while true; do
        local status
        status=$(docker inspect --format '{{.State.Health.Status}}' "$container" 2>/dev/null || echo "none")
        if [ "$status" = "healthy" ]; then
            log "Container '$container' is healthy."
            return 0
        fi
        if [ "$(date +%s)" -ge "$deadline" ]; then
            log "Container '$container' did not become healthy within ${HEALTH_TIMEOUT}s (last status: $status)."
            return 1
        fi
        sleep 5
    done
}

# True zero-downtime blue-green deploy for the backend service.
# Flow: start green → wait healthy → nginx reload (cut traffic) →
#       drain old → stop blue → recreate compose backend → nginx reload back → rm green
deploy_backend_blue_green() {
    log "---------- Blue-green rolling update: backend ----------"

    # If backend_proxy is not running (first deploy or new service added),
    # bring up the full stack normally before attempting blue-green logic.
    local proxy_id
    proxy_id=$(${COMPOSE_CMD} ps -q backend_proxy 2>/dev/null | head -1 || echo "")
    if [ -z "$proxy_id" ]; then
        log "backend_proxy not running — performing initial stack start."
        ${COMPOSE_CMD} up -d backend backend_proxy
        wait_healthy "backend"
        return 0
    fi

    # If backend itself is not running, start it and return.
    local existing
    existing=$(${COMPOSE_CMD} ps -q backend 2>/dev/null | head -1 || echo "")
    if [ -z "$existing" ]; then
        log "No existing backend — performing initial start."
        ${COMPOSE_CMD} up -d --no-deps backend
        wait_healthy "backend"
        return 0
    fi

    # 1. Start the green (new-image) container on the same docker network.
    log "Starting green container: $GREEN_CONTAINER"
    docker run -d \
        --name "$GREEN_CONTAINER" \
        --network "$NETWORK_NAME" \
        --env-file "$BACKEND_ENV_FILE" \
        --health-cmd 'python3 -c "import urllib.request; urllib.request.urlopen(\"http://localhost:8000/api/health\")" || exit 1' \
        --health-interval 10s \
        --health-timeout 5s \
        --health-retries 3 \
        --health-start-period 30s \
        "$BACKEND_IMAGE"

    # 2. Wait for green to pass health check before touching anything live.
    if ! wait_healthy_container "$GREEN_CONTAINER"; then
        docker rm -f "$GREEN_CONTAINER" || true
        fail "Green backend failed health check — aborting, original backend still running."
    fi

    # 3. Atomically cut nginx to the green container.
    #    nginx -s reload is graceful: old workers finish their current requests
    #    before exiting; new workers pick up the updated upstream immediately.
    log "Switching nginx upstream to green container..."
    cat > nginx-upstream.conf << EOF
# Active upstream for the TripBuddy backend.
# Managed by deploy.sh during rolling deploys — do not edit manually.
upstream backend_upstream {
    server ${GREEN_CONTAINER}:8000;
    keepalive 32;
}
EOF
    ${COMPOSE_CMD} exec -T backend_proxy nginx -s reload
    log "Nginx reloaded — new requests now routed to green container."

    # 4. Brief drain window so any in-flight requests on the old backend finish.
    sleep 5

    # 5. Gracefully stop the old backend.
    #    stop_grace_period: 60s in compose gives uvicorn time to finish LLM calls.
    log "Stopping old backend (graceful shutdown)..."
    ${COMPOSE_CMD} stop backend

    # 6. Recreate the backend compose service with the new image.
    log "Recreating backend compose service with new image..."
    ${COMPOSE_CMD} up -d --no-deps backend

    # 7. Verify the recreated backend passes health checks.
    if ! wait_healthy "backend"; then
        # Green is still running and serving traffic — leave it up as fallback.
        fail "Recreated backend failed health check. Green container ($GREEN_CONTAINER) is still active."
    fi

    # 8. Switch nginx back to the stable compose service name.
    log "Switching nginx back to compose backend service..."
    cat > nginx-upstream.conf << EOF
# Active upstream for the TripBuddy backend.
# Managed by deploy.sh during rolling deploys — do not edit manually.
upstream backend_upstream {
    server backend:8000;
    keepalive 32;
}
EOF
    ${COMPOSE_CMD} exec -T backend_proxy nginx -s reload

    # 9. Remove the green container now that compose backend is live.
    docker rm -f "$GREEN_CONTAINER" || true
    log "Backend blue-green deploy complete. Green container removed."
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
# Step 1a: Backend — true blue-green via nginx upstream swap
# ---------------------------------------------------------------------------
# Green container starts with new image → health check passes → nginx reloads
# (graceful: existing requests finish on old workers) → old container drains
# → compose backend recreated → nginx reloads back → green removed.
deploy_backend_blue_green

# ---------------------------------------------------------------------------
# Step 1b: Frontend — health-check gated rolling update
# ---------------------------------------------------------------------------
log "---------- Rolling update: frontend ----------"
${COMPOSE_CMD} up -d --no-deps --pull missing frontend

if ! wait_healthy "frontend"; then
    log "Frontend health check failed. Rolling back frontend to latest..."
    FRONTEND_IMAGE="tripbuddy-frontend:latest" \
    ${COMPOSE_CMD} up -d --no-deps frontend || true
    fail "Deployment aborted after failed health check on 'frontend'."
fi

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
