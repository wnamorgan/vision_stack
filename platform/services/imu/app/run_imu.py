# platform/services/imu/app/run_imu.py

import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
import multiprocessing as mp

import zmq

# --- path handling similar to other services ---
SERVICE_ROOT = Path(__file__).resolve().parents[1]   # .../imu
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(SERVICE_ROOT / "code"))      # so `code/` imports work

log = logging.getLogger("imu")

ZMQ_BIND_PUB_IMU_HOST = os.getenv("ZMQ_BIND_PUB_IMU_HOST", "0.0.0.0")
ZMQ_BIND_PUB_IMU_PORT = int(os.getenv("ZMQ_BIND_PUB_IMU_PORT", "5530"))
ZMQ_IMU_PUB_ENDPOINT = f"tcp://{ZMQ_BIND_PUB_IMU_HOST}:{ZMQ_BIND_PUB_IMU_PORT}"

# Optional tuning
IMU_QUEUE_MAX = int(os.getenv("IMU_QUEUE_MAX", "10000"))
ZMQ_SNDHWM = int(os.getenv("ZMQ_SNDHWM", "10000"))

def imu_worker(shutdown_event, out_q):
    from hwif.imu import imu
    imu_if = imu(shutdown_event)
    imu_if.subscribe(out_q)
    imu_if.run()

def main():
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    mp.set_start_method("spawn", force=True)

    shutdown_event = mp.Event()

    def _handle_sigterm(_signum, _frame):
        log.info("SIGTERM/SIGINT -> shutdown_event.set()")
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    # Start IMU worker in its own process
    msg_q: mp.Queue = mp.Queue(maxsize=IMU_QUEUE_MAX)
    imu_proc = mp.Process(target=imu_worker, args=(shutdown_event, msg_q), name="imu")
    imu_proc.start()
    time.sleep(0.1)
    log.info(f"imu_proc started: pid={imu_proc.pid}, alive={imu_proc.is_alive()}")

    # ZMQ PUB
    ctx = zmq.Context.instance()
    pub = ctx.socket(zmq.PUB)
    pub.setsockopt(zmq.SNDHWM, ZMQ_SNDHWM)
    pub.bind(ZMQ_IMU_PUB_ENDPOINT)
    log.info(f"IMU ZMQ PUB bound: {ZMQ_IMU_PUB_ENDPOINT}")

    info_period = float(os.getenv("INFO_PERIOD", "10.0"))
    last_log_t = time.time()
    count = 0

    try:
        while not shutdown_event.is_set():
            # Block for the next message; do NOT drain.
            try:
                msg = msg_q.get(timeout=0.5)
            except Exception:
                continue

            topic = str(msg.get("topic", "imu")).encode("utf-8")
            payload = json.dumps(msg, separators=(",", ":")).encode("utf-8")

            # send every message in order
            pub.send_multipart([topic, payload])

            count += 1
            now = time.time()
            if now - last_log_t >= info_period:
                hz = count / (now - last_log_t)
                log.info(f"publishing ~{hz:.1f} Hz")
                last_log_t = now
                count = 0

    finally:
        shutdown_event.set()
        if imu_proc.is_alive():
            imu_proc.join(timeout=2.0)
            if imu_proc.is_alive():
                imu_proc.terminate()

        pub.close(0)
        ctx.term()


if __name__ == "__main__":
    main()
