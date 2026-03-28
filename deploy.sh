#!/bin/bash
# Deploys TripBuddy to Docker Swarm using docker stack deploy.
# Swarm handles rolling updates natively via deploy.update_config in the compose file.

set -euo pipefail

ENV_FILE="${ENV_FILE:-.env.prod}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
STACK_NAME="${STACK_NAME:-tripbuddy}"

if [ ! -f "$ENV_FILE" ]; then
    echo "[deploy] ERROR: Environment file not found: $ENV_FILE" >&2
    exit 1
fi

# Load env vars so image name variables are available to docker stack deploy
set -a; source "$ENV_FILE"; set +a

# Allow CI pipeline to override individual image names via env vars
BACKEND_IMAGE="${BACKEND_IMAGE:-tripbuddy-backend:latest}"
FRONTEND_IMAGE="${FRONTEND_IMAGE:-tripbuddy-frontend:latest}"
PROMETHEUS_IMAGE="${PROMETHEUS_IMAGE:-tripbuddy-prometheus:latest}"
GRAFANA_IMAGE="${GRAFANA_IMAGE:-tripbuddy-grafana:latest}"

export BACKEND_IMAGE FRONTEND_IMAGE PROMETHEUS_IMAGE GRAFANA_IMAGE

echo "[deploy] Deploying stack '$STACK_NAME'"
echo "[deploy]   backend   : $BACKEND_IMAGE"
echo "[deploy]   frontend  : $FRONTEND_IMAGE"
echo "[deploy]   prometheus: $PROMETHEUS_IMAGE"
echo "[deploy]   grafana   : $GRAFANA_IMAGE"

# Remove any leftover bridge network from a previous docker compose setup.
# Swarm needs to create an overlay network with the same name; a pre-existing
# bridge network causes `docker stack deploy` to fail.
if docker network inspect "${STACK_NAME}_default" --format '{{.Driver}}' 2>/dev/null | grep -qv overlay; then
    echo "[deploy] Removing legacy non-overlay network ${STACK_NAME}_default..."
    docker network rm "${STACK_NAME}_default" 2>/dev/null || true
fi

# --with-registry-auth forwards registry credentials to Swarm nodes so they
# can pull private images without needing a separate docker login on each node.
docker stack deploy --with-registry-auth -c "$COMPOSE_FILE" "$STACK_NAME"

echo "[deploy] Stack deployed. Services:"
docker stack services "$STACK_NAME"

echo "[deploy] Done."
# (Swarm handles rolling restarts; no health-poll loop needed here.)
