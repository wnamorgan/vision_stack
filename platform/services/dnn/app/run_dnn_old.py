#!/usr/bin/env python3

import os
import sys
import time
import json
from pathlib import Path
from multiprocessing import shared_memory
import logging
import zmq
import numpy as np


# Match camera/gateway layout
SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))


def env(name, default):
    return os.getenv(name, default)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [dnn] %(message)s",
    )
    log = logging.getLogger("dnn")

    ctx = zmq.Context()

    # ---- Camera SUB (exact same pattern as gateway)
    cam_ep = f"tcp://{env('ZMQ_CONNECT_SUB_CAMERA_HOST','camera')}:{env('ZMQ_CONNECT_SUB_CAMERA_PORT','5555')}"
    sub = ctx.socket(zmq.SUB)
    sub.connect(cam_ep)
    sub.setsockopt_string(zmq.SUBSCRIBE, "")

    # ---- Detections PUB (stub)
    det_ep = f"tcp://{env('ZMQ_BIND_PUB_DET_HOST','0.0.0.0')}:{env('ZMQ_BIND_PUB_DET_PORT','5566')}"
    pub = ctx.socket(zmq.PUB)
    pub.bind(det_ep)

    shm = None
    buf = None
    last_log = time.time()
    frames = 0
    while True:
        msg = sub.recv_json()   # block, exactly like gateway

        # camera schema (current)
        shm_name = msg["shm_name"]
        md = msg.get("metadata", {})
        w = md["width"]
        h = md["height"]
        c = md.get("channels", 3)
        frame_id = md.get("frame_id")
        
        if shm is None:
            shm = shared_memory.SharedMemory(name=shm_name)
            buf = np.ndarray((h, w, c), dtype=np.uint8, buffer=shm.buf)

        # copy immediately (same assumption as gateway)
        frame = buf[:h, :w, :c].copy()
        frames += 1

        now = time.time()
        if now - last_log >= 1.0:
            log.info("rx camera frames: %d/s (last frame_id=%s)", frames, frame_id)
            frames = 0
            last_log = now
        # ---- stub detection output
        out = {
            "type": "detections",
            "frame_id": frame_id,
            "dets": []
        }

        pub.send_json(out)


if __name__ == "__main__":
    main()
