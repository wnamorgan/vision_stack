import signal
import time
import multiprocessing as mp

from .imu_sim import imu_loop
from .dnn_sim import dnn_loop
from .camera_sim import camera_loop


def run():
    mp.set_start_method("spawn", force=True)
    stop_event = mp.Event()

    def _handle_sigterm(_signum, _frame):
        stop_event.set()

    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    procs = [
        mp.Process(target=imu_loop, name="imu_sim", args=(stop_event,)),
        mp.Process(target=dnn_loop, name="dnn_sim", args=(stop_event,)),
        mp.Process(target=camera_loop, name="camera_sim", args=(stop_event,)),
    ]

    for p in procs:
        p.start()

    try:
        while not stop_event.is_set():
            time.sleep(0.2)
    finally:
        stop_event.set()
        for p in procs:
            p.join(timeout=2.0)
            if p.is_alive():
                p.terminate()
