# syntax=docker/dockerfile:1.4
ARG BASE_IMAGE=ultralytics/ultralytics:latest-jetson-jetpack6
FROM ${BASE_IMAGE}

WORKDIR /app

# Basic tools (keep if you liked having them)
RUN apt-get update && apt-get install -y --no-install-recommends \
    nano git htop unzip \
    && rm -rf /var/lib/apt/lists/*

# DNN container needs: ZMQ + SHM reader glue; keep CUDA/TRT from the base image
RUN python3 -m pip install --no-cache-dir --upgrade pip wheel && \
    python3 -m pip install --no-cache-dir pyzmq numpy psutil

# If you need OpenCV in-container for debug overlays, keep your arch-aware pattern;
# otherwise prefer opencv-python-headless and remove GUI deps later.
ARG TARGETARCH
RUN if [ "$TARGETARCH" = "amd64" ]; then \
        python3 -m pip uninstall -y opencv-python-headless || true && \
        python3 -m pip install --no-cache-dir opencv-python ; \
    else \
        apt-get update && apt-get install -y --no-install-recommends \
            python3-opencv libgtk2.0-dev libgtk-3-dev && \
        rm -rf /var/lib/apt/lists/* && \
        python3 -m pip uninstall -y opencv-python opencv-python-headless || true ; \
    fi

COPY . /app
CMD ["python3", "app/run_dnn.py"]