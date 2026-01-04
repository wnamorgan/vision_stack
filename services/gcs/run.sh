#!/usr/bin/env bash
set -e

IMAGE_NAME=vision_stack-gcs
ENV_FILE=.env

docker run --rm -it \
  --network host \
  --env-file ${ENV_FILE} \
  -v $(pwd):/app \
  ${IMAGE_NAME} \
  python run_gcs.py
