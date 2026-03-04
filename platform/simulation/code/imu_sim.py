import json
import os
import time
import logging

import zmq
from code.util.gw_register import start_gateway_registration


def _env_float(name, default):
    value = os.getenv(name)
    return float(value) if value else default


def imu_loop(stop_event):
    host = os.getenv("ZMQ_BIND_PUB_IMU_HOST", "0.0.0.0")
    port = int(os.getenv("ZMQ_BIND_PUB_IMU_PORT", "5530"))
    hz = _env_float("SIM_IMU_HZ", 100.0)
    temp_c = _env_float("SIM_IMU_TEMP_C", 42.0)
    info_period = _env_float("INFO_PERIOD", 10.0)

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    log = logging.getLogger("imu_sim")

    ctx = zmq.Context.instance()
    pub = ctx.socket(zmq.PUB)
    pub.bind(f"tcp://{host}:{port}")
    log.info("IMU ZMQ PUB bound: tcp://%s:%s", host, port)
    log.info("SIM_IMU_HZ=%s SIM_IMU_TEMP_C=%s", hz, temp_c)

    endpoint = f"tcp://{os.getenv('GW_REGISTER_SUB_HOST','simulation')}:{os.getenv('GW_REGISTER_SUB_PORT', str(port))}"
    stream = os.getenv("GW_REGISTER_STREAM_IMU", "").strip()
    start_gateway_registration(endpoint=endpoint, logger=log, stream=stream)

    period = 1.0 / max(1.0, hz)
    counter = 0
    t0 = time.time()
    next_tick = time.monotonic()
    last_log_t = time.time()
    count = 0

    try:
        while not stop_event.is_set():
            now = time.time()
            payload = {
                "timestamp": now - t0,
                "t_imu_sw_ns": time.time_ns(),
                "gyro": [0.0, 0.0, 0.0],
                "accel": [0.0, 0.0, 1.0],
                "counter": counter,
                "temp": temp_c,
            }
            msg = {"tx": "imu", "rx": "*", "topic": "gaa", "payload": payload}
            pub.send_multipart([b"gaa", json.dumps(msg, separators=(",", ":")).encode("utf-8")])
            counter += 1
            count += 1
            if now - last_log_t >= info_period:
                rate = count / (now - last_log_t)
                log.info("publishing ~%.1f Hz", rate)
                last_log_t = now
                count = 0
            next_tick += period
            sleep_s = next_tick - time.monotonic()
            if sleep_s > 0:
                time.sleep(sleep_s)
            else:
                next_tick = time.monotonic()
    finally:
        pub.close(0)
        ctx.term()
