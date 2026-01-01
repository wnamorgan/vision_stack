#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/.env"

IMAGE_NAME="${CAMERA_IMAGE:-vision_stack-camera}"

docker run --rm \
    --env-file "${SCRIPT_DIR}/.env" \
    -v "${SCRIPT_DIR}:/app" \
    --ipc=host \
    --network=host \
    --device "${CAM_DEVICE}:${CAM_DEVICE}" \
    --name "vision-stack-camera" \
    "${IMAGE_NAME}"
