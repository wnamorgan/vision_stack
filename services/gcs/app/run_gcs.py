import multiprocessing as mp
import sys
from pathlib import Path
SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from code.video_process import run as video_run
from code.api_process import run as api_run
from code.udp_publisher import run as udp_run
from code.dash_process import run as dash_run
from code.udp_rx_process import run as udp_rx_run


def main():
    mp.set_start_method("spawn")

    procs = [
        mp.Process(target=video_run, name="video"),
        mp.Process(target=api_run, name="api"),
        mp.Process(target=udp_run, name="udp"),
        mp.Process(target=dash_run, name="dash"),
        mp.Process(target=udp_rx_run, name="udp_rx"),
    ]

    for p in procs:
        p.start()

    for p in procs:
        p.join()    

if __name__ == "__main__":
    main()
