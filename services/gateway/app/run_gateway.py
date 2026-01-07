import multiprocessing as mp
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from code.rtp_tx_process import run as rtp_run
from code.udp_rx_process import run as udp_run
from code.control_handler import run as control_run

if __name__ == "__main__":
    mp.set_start_method("spawn")

    procs = [
        mp.Process(target=rtp_run, name="rtp_tx"),
        mp.Process(target=udp_run, name="udp_rx"),
        mp.Process(target=control_run, name="control"),
    ]

    for p in procs:
        p.start()

    for p in procs:
        p.join()
