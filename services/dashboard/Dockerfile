FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

# System deps for PyGObject + OpenCV-headless
RUN apt-get update && apt-get install -y \
    build-essential \
    pkg-config \
    python3-dev \
    libglib2.0-dev \
    libcairo2-dev \
    gobject-introspection \
    libgirepository1.0-dev \
    gir1.2-glib-2.0 \
    gir1.2-gstreamer-1.0 \
    python3-gi \
    python3-gi-cairo \
    libgl1 \
    libglib2.0-0 \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-libav \
    && rm -rf /var/lib/apt/lists/*

# Python tooling
RUN pip install --upgrade pip wheel

# Python deps (pin PyGObject for Debian)
RUN pip install \
    numpy \
    pyzmq \
    opencv-python-headless \
    pycairo \
    "PyGObject<3.46"

WORKDIR /app

COPY . /app

CMD ["bash"]
