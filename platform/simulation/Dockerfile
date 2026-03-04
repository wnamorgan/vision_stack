FROM python:3.11-slim

WORKDIR /app

RUN python -m pip install --no-cache-dir --upgrade pip \
  && python -m pip install --no-cache-dir pyzmq numpy

COPY . /app

ENV PYTHONUNBUFFERED=1

CMD ["python3", "app/run_sim.py"]
#CMD ["bash", "-lc", "sleep infinity"]
