import multiprocessing
import time
from pathlib import Path
import sys
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hwif.imu import imu
from test.imu_dash import launch_dash

def monitor(queue):
    while True:
        try:
            msg = queue.get(timeout=1)
            print(f"[main] Message received at {time.time():.3f} with imu timestamp {msg['timestamp']:.3f}")
        except multiprocessing.queues.Empty:
            continue
        except KeyboardInterrupt:
            break

def _request_child_stop(proc) -> None:
    proc.join(timeout=1)         # give it a chance to exit cleanly

    if proc.is_alive():          # last-ditch fallback
        print("Child still alive → calling terminate()")
        proc.terminate()
        proc.join()

def main():
    shutdown_event = multiprocessing.Event()
    msg_queue = multiprocessing.Queue()

    imu_IF = imu(shutdown_event)
    imu_IF.subscribe(msg_queue)

    imu_proc = multiprocessing.Process(target=imu_IF.run)
    imu_proc.start()

    try:
        #monitor(msg_queue)
        launch_dash(msg_queue)
    except KeyboardInterrupt:
        print("KeyboardInterrupt → shutting down…")
    finally:
        shutdown_event.set() 
        _request_child_stop(imu_proc)


if __name__=="__main__":
    main()