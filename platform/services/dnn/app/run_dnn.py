#!/usr/bin/env python3

import multiprocessing as mp
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from code.dnn_worker import run as dnn_run

if __name__ == "__main__":
    mp.set_start_method("spawn")

    procs = [
        mp.Process(target=dnn_run, name="dnn_worker"),
    ]

    for p in procs:
        p.start()

    for p in procs:
        p.join()
