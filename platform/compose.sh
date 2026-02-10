#!/usr/bin/env bash
set -euo pipefail

ARCH="$(uname -m)"
if [[ "$ARCH" == "x86_64" ]]; then
  export TRACKER_BASE_IMAGE="ultralytics/ultralytics:latest"
  export TRACKER_TAG="x86_64"
else
  # Jetson/Orin
  export TRACKER_BASE_IMAGE="ultralytics/ultralytics:latest-jetson-jetpack6"
  export TRACKER_TAG="aarch64"
fi

# pass-through everything (up/down/build/logs/--remove-orphans/service selection)
exec docker compose -f docker-compose.yml "$@"
