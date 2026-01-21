import multiprocessing as mp
import sys
from pathlib import Path
SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))


from code.udp_rx_process import run as udp_rx_run
from code.udp_publisher import run as udp_run
from code.rtp_rx_to_shm_process import run as rtp_rx_shm_run

def main():
    mp.set_start_method("spawn")

    procs = [
        mp.Process(target=udp_rx_run, name="udp_rx"),
        mp.Process(target=udp_run, name="udp"),
        mp.Process(target=rtp_rx_shm_run, name="rtp_rx_shm"),
    ]

    for p in procs:
        p.start()

    for p in procs:
        p.join()    

    # import time
    # while True:
    #     time.sleep(1)

if __name__ == "__main__":
    main()
