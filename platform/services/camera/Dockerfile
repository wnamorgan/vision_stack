FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
        python3 \
        python3-pip \
        python3-gi \
        libglib2.0-dev \
        cmake \
        libusb-1.0-0-dev \
        gobject-introspection \
        libgtk-3-dev \
        gtk-doc-tools \
        xsltproc \
        libgstreamer1.0-dev \
        libgstreamer-plugins-base1.0-dev \
        libgstreamer-plugins-good1.0-dev \
        libgirepository1.0-dev \
        gettext \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-bad \
        libcanberra-gtk-module \
        libcanberra-gtk3-module \
        udev \
        wget \
        libxml2-dev \
        usbutils \
        python3-tk \
        ninja-build \
    && rm -rf /var/lib/apt/lists/*

RUN /usr/bin/python3 -m pip install --no-cache-dir \
        "meson>=0.57" \
        numpy \
        pyzmq \
        opencv-python-headless

RUN wget https://github.com/AravisProject/aravis/releases/download/0.8.31/aravis-0.8.31.tar.xz -O /opt/aravis.tar.xz \
    && mkdir /opt/aravis \
    && tar -xf /opt/aravis.tar.xz -C /opt/aravis --strip-components=1 \
    && rm /opt/aravis.tar.xz

WORKDIR /opt/aravis
RUN meson build --prefix=/usr
RUN ninja -C build
RUN ninja -C build install
RUN ldconfig

WORKDIR /app
COPY . /app

CMD ["/usr/bin/python3", "app/run_camera.py"]
