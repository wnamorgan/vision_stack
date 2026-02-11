import os
import time
import logging

import zmq


def _env_float(name, default):
    value = os.getenv(name)
    return float(value) if value else default


def _env_int(name, default):
    value = os.getenv(name)
    return int(value) if value else default


def camera_loop(stop_event):
    host = os.getenv("ZMQ_BIND_PUB_CAMERA_HOST", "0.0.0.0")
    port = int(os.getenv("ZMQ_BIND_PUB_CAMERA_PORT", "5555"))
    hz = _env_float("SIM_CAM_HZ", 15.0)
    width = _env_int("SIM_CAM_W", 1280)
    height = _env_int("SIM_CAM_H", 720)
    channels = _env_int("SIM_CAM_C", 3)
    info_period = _env_float("INFO_PERIOD", 10.0)

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    log = logging.getLogger("camera_sim")

    ctx = zmq.Context.instance()
    pub = ctx.socket(zmq.PUB)
    pub.bind(f"tcp://{host}:{port}")
    log.info("CAM ZMQ PUB bound: tcp://%s:%s", host, port)
    log.info("SIM_CAM_HZ=%s SIM_CAM_W=%s SIM_CAM_H=%s SIM_CAM_C=%s", hz, width, height, channels)

    period = 1.0 / max(1.0, hz)
    frame_id = 0
    last_log_t = time.time()
    count = 0

    try:
        next_tick = time.monotonic()
        while not stop_event.is_set():
            now_ns = time.time_ns()
            msg = {
                "type": "frame",
                "source": "sim_camera",
                "frame_id": frame_id,
                "metadata": {
                    "frame_id": frame_id,
                    "t_cam_hw_ns": now_ns,
                    "t_cam_sw_ns": now_ns,
                    "w": width,
                    "h": height,
                    "c": channels,
                },
            }
            pub.send_json(msg)
            frame_id += 1
            count += 1
            now = time.time()
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
