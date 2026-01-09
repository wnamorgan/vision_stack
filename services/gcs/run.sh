#!/usr/bin/env bash
set -e

IMAGE_NAME=vision_stack-gcs
ENV_FILE=.env

docker run --rm -it \
  --network host \
  --env-file ${ENV_FILE} \
  -v $(pwd)/app:/app \
  -v $(pwd)/code:/app/code \
  -v $(pwd)/static:/app/static \
  ${IMAGE_NAME} \
  python run_gcs.py
