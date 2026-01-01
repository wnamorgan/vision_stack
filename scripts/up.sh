#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export COMPOSE_DOCKER_CLI_BUILD=1
export DOCKER_BUILDKIT=1

CAM_DEVICE="${CAM_DEVICE:-}"

if [[ -z "${CAM_DEVICE}" ]]; then
  for i in {0..9}; do
    if [[ -e "/dev/video${i}" ]]; then
      CAM_DEVICE="/dev/video${i}"
      break
    fi
  done
fi

# fall back if still empty
CAM_DEVICE="${CAM_DEVICE:-/dev/video0}"

export CAM_DEVICE

cache_env="${ROOT}/.env"
if ! grep -q '^CAM_DEVICE=' "${cache_env}" 2>/dev/null; then
  printf 'CAM_DEVICE=%s\n' "${CAM_DEVICE}" >> "${cache_env}"
fi

cd "${ROOT}"
docker compose up
