#!/usr/bin/env bash
set -euo pipefail

set -a
source .env
set +a

NETWORK_NAME="lan"
MODE="default"
ARGS=()

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

for arg in "$@"; do
  if [[ "$arg" == "--wifi" ]]; then
    MODE="wifi"
  else
    ARGS+=("$arg")
  fi
done

if [[ "$MODE" == "wifi" ]]; then
  echo "Mode: wifi (using docker-compose.wifi.yml override)"
  COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.wifi.yml)
else
  echo "Mode: default"
  ensure_lan_network
  COMPOSE_FILES=(-f docker-compose.yml)
fi

if [[ "${ARGS[0]:-}" == "down" ]]; then
  exec docker compose "${COMPOSE_FILES[@]}" down --remove-orphans
fi

exec docker compose "${COMPOSE_FILES[@]}" "${ARGS[@]}"
