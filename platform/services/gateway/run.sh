#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/.env"

IMAGE_NAME="${GATEWAY_IMAGE:-vision_stack-gateway}"

FORCE_LOCAL=${FORCE_LOCAL:-0}
LOCAL_HOST=${LOCAL_HOST:-localhost}
LOCAL_PORT=${LOCAL_PORT:-5555}

docker run --rm \
    --env-file "${SCRIPT_DIR}/.env" \
    -e "ZMQ_CONNECT_SUB_CAMERA_HOST=$(if [ "${FORCE_LOCAL}" = "1" ]; then echo "${LOCAL_HOST}"; else echo "${ZMQ_CONNECT_SUB_CAMERA_HOST}"; fi)" \
    -e "ZMQ_CONNECT_SUB_CAMERA_PORT=$(if [ "${FORCE_LOCAL}" = "1" ]; then echo "${LOCAL_PORT}"; else echo "${ZMQ_CONNECT_SUB_CAMERA_PORT}"; fi)" \
    -v "${SCRIPT_DIR}:/app" \
    --ipc=host \
    --network=host \
    --name "vision-stack-gateway" \
    "${IMAGE_NAME}"
