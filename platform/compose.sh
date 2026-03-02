#!/usr/bin/env bash
set -euo pipefail

COMPOSE_PROFILES_DEFAULT="prod"
ENV_FILE=".env"

ARCH="$(uname -m)"
if [[ "$ARCH" == "x86_64" ]]; then
  export TRACKER_BASE_IMAGE="ultralytics/ultralytics:latest"
  export TRACKER_TAG="x86_64"
else
  # Jetson/Orin
  export TRACKER_BASE_IMAGE="ultralytics/ultralytics:latest-jetson-jetpack6"
  export TRACKER_TAG="aarch64"
fi

if [[ "${1:-}" == "--sim" ]]; then
  shift
  export COMPOSE_PROFILES="sim"
  ENV_FILE=".env.sim"
else
  export COMPOSE_PROFILES="${COMPOSE_PROFILES_DEFAULT}"
fi

set -a
source "${ENV_FILE}"
set +a

NETWORK_NAME="lan"

ensure_lan_network() {
  if docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
    return
  fi

  echo "Creating ${NETWORK_NAME}..."
  docker network create -d macvlan \
    --subnet=192.168.1.0/24 \
    --gateway=192.168.1.1 \
    -o parent="${MACVLAN_PARENT}" \
    "${NETWORK_NAME}"
}

ensure_lan_network

# pass-through everything (up/down/build/logs/--remove-orphans/service selection)
exec docker compose -f docker-compose.yml --env-file "$ENV_FILE" "$@"
