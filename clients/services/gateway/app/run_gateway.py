import multiprocessing as mp
import sys
from pathlib import Path
SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))


from code.udp_rx_process import run as udp_rx_run


def main():
    mp.set_start_method("spawn")

    procs = [
        mp.Process(target=udp_rx_run, name="udp_rx"),
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
