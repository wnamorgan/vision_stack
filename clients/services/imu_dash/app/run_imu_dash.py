import multiprocessing as mp
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from code.api_process import run as api_run
from code.dash_process import run as dash_run


def main():
    mp.set_start_method("spawn")
    procs = [
        mp.Process(target=api_run, name="imu_api"),
        mp.Process(target=dash_run, name="imu_dash"),
    ]

    for p in procs:
        p.start()

    for p in procs:
        p.join()


if __name__ == "__main__":
    main()
