#!/usr/bin/env python3

import multiprocessing as mp
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from code.dnn_worker import run as dnn_run
from code.tracker_sm import run as tracker_sm_run

if __name__ == "__main__":
    mp.set_start_method("spawn")

    procs = [
        mp.Process(target=dnn_run, name="dnn_worker"),
        mp.Process(target=tracker_sm_run, name="tracker_sm"),
    ]

    for p in procs:
        p.start()

    for p in procs:
        p.join()
