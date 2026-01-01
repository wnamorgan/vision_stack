#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/.env"

IMAGE_NAME="${DASHBOARD_IMAGE:-vision_stack-dashboard}"

docker run --rm -it \
    --env-file "${SCRIPT_DIR}/.env" \
    -v "${SCRIPT_DIR}:/app" \
    --ipc=host \
    --network=host \
    --device=/dev/video0 \
    --name "vision-stack-dashboard" \
    "${IMAGE_NAME}"
