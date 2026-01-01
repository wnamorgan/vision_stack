#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/.env"

IMAGE_NAME="${DASHBOARD_IMAGE:-vision_stack-dashboard}"

FORCE_LOCAL=${FORCE_LOCAL:-0}
LOCAL_ENDPOINT=${LOCAL_ENDPOINT:-tcp://localhost:5555}

docker run --rm \
    --env-file "${SCRIPT_DIR}/.env" \
    -e "ZMQ_SUB_ENDPOINT=$(if [ "${FORCE_LOCAL}" = "1" ]; then echo "${LOCAL_ENDPOINT}"; else echo "${ZMQ_SUB_ENDPOINT}"; fi)" \
    -v "${SCRIPT_DIR}:/app" \
    --ipc=host \
    --network=host \
    --name "vision-stack-dashboard" \
    "${IMAGE_NAME}"
