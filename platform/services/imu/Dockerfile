FROM python:3.11

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip wheel && \
    pip install --no-cache-dir \
      pyzmq \
      pyserial \
      numpy \
      psutil

WORKDIR /app
COPY . /app

#CMD ["bash", "-lc", "sleep infinity"]
CMD ["python3", "app/run_imu.py"]
