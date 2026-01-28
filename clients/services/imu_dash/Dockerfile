FROM python:3.9

ENV DEBIAN_FRONTEND=noninteractive

RUN pip install --upgrade pip wheel

RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    pyzmq \
    requests \
    pydantic \
    dash \
    dash-bootstrap-components

WORKDIR /app
COPY . /app

CMD ["python", "run_imu_dash.py"]
