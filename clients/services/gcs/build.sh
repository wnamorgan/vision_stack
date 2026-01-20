#!/usr/bin/env bash
set -e

IMAGE_NAME=vision_stack-gcs

docker build -t ${IMAGE_NAME} .
