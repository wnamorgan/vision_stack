import os
import time
import logging
import threading
import queue
from multiprocessing import shared_memory
from pathlib import Path

import zmq
import numpy as np
import torch

from . import util


def env(name, default):
    return os.getenv(name, default)


class DnnWorker:
    def __init__(self):
        self.stop_event = threading.Event()

        # queues: keep latest only
        self.frame_queue = queue.Queue(maxsize=1)  # latest frame from ZMQ ingest
        self.preproc_queue = queue.Queue(maxsize=1)  # latest preprocessed frame

        # ZMQ
        self.context = zmq.Context()
        self.sub_socket = self.context.socket(zmq.SUB)
        cam_ep = (
            f"tcp://{env('ZMQ_CONNECT_SUB_CAMERA_HOST','camera')}:"
            f"{env('ZMQ_CONNECT_SUB_CAMERA_PORT','5555')}"
        )
        self.sub_socket.connect(cam_ep)
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")
        self.sub_socket.RCVTIMEO = 200  # ms

        self.pub_socket = self.context.socket(zmq.PUB)
        det_ep = f"tcp://{env('ZMQ_BIND_PUB_DET_HOST','0.0.0.0')}:{env('ZMQ_BIND_PUB_DET_PORT','5566')}"
        self.pub_socket.bind(det_ep)

        # SHM
        self.shm = None
        self.image_buf = None
        self.max_height = int(env("DNN_MAX_HEIGHT", "4320"))
        self.max_width = int(env("DNN_MAX_WIDTH", "7680"))

        # logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [dnn] %(message)s",
        )
        self.log = logging.getLogger("dnn")

        # stats
        self.frame_id = 0
        self._last_log = time.time()
        self._frames = 0
        self._infer_time_s = 0.0
        self.info_period = float(env("INFO_PERIOD", "1.0"))

        # model
        service_root = Path(__file__).resolve().parents[1]
        model_name = env("DNN_MODEL_NAME", "yolo11n_toy_cars_190.pt")
        model_path = (service_root / "models" / model_name).resolve()
        self.conf_thres = float(env("DNN_CONF_THRESH", "0.75"))
        self.log.info("Loading model from %s", model_path)
        self.model = util.get_model(model_path)

    def run(self):
        ingest_thread = threading.Thread(target=self.zmq_sub_loop, daemon=True)
        preproc_thread = threading.Thread(target=self.preprocess_loop, daemon=True)
        infer_thread = threading.Thread(target=self.infer_loop, daemon=True)

        ingest_thread.start()
        preproc_thread.start()
        infer_thread.start()

        try:
            while not self.stop_event.is_set():
                time.sleep(0.2)
        finally:
            self.stop_event.set()
            ingest_thread.join(timeout=1.0)
            preproc_thread.join(timeout=1.0)
            infer_thread.join(timeout=1.0)

            try:
                if self.shm is not None:
                    self.shm.close()
            except Exception:
                pass

            try:
                self.sub_socket.close()
            except Exception:
                pass
            try:
                self.pub_socket.close()
            except Exception:
                pass
            try:
                self.context.term()
            except Exception:
                pass

    # ----------------------------
    # ZMQ ingest + SHM
    # ----------------------------
    def enqueue_frame(self, msg: dict):
        shm_name = msg["shm_name"]
        md = msg.get("metadata", {})
        width = int(md["w"])
        height = int(md["h"])
        channels = int(md.get("c", 3))
        frame_id = md.get("frame_id")

        # first frame: attach to SHM
        if self.shm is None:
            self.shm = shared_memory.SharedMemory(name=shm_name)
            self.image_buf = np.ndarray(
                (self.max_height, self.max_width, channels),
                dtype=np.uint8,
                buffer=self.shm.buf[: self.max_width * self.max_height * channels],
            )

        # copy semantics preserved
        image = self.image_buf[:height, :width, :channels].copy()

        self.frame_id += 1
        frame = (image, msg, frame_id)

        # keep latest only
        try:
            self.frame_queue.put_nowait(frame)
        except queue.Full:
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                pass
            self.frame_queue.put_nowait(frame)

    def zmq_sub_loop(self):
        while not self.stop_event.is_set():
            try:
                msg = self.sub_socket.recv_json()
            except zmq.Again:
                continue

            if msg.get("type") == "frame":
                self.enqueue_frame(msg)

    # ----------------------------
    # Preprocess (pass-through for now)
    # ----------------------------
    def preprocess_loop(self):
        while not self.stop_event.is_set():
            try:
                frame = self.frame_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            # placeholder for resize/tiling; passthrough for now
            try:
                self.preproc_queue.put_nowait(frame)
            except queue.Full:
                try:
                    self.preproc_queue.get_nowait()
                except queue.Empty:
                    pass
                self.preproc_queue.put_nowait(frame)

    # ----------------------------
    # Inference (stub)
    # ----------------------------
    def infer_loop(self):
        while not self.stop_event.is_set():
            try:
                frame, msg, frame_id = self.preproc_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            t0 = time.time()
            results = self.model(
                frame,
                device=util.DEVICE,
                imgsz=util.IMG_SIZE,
                conf=self.conf_thres,
                verbose=False,
            )
            if torch.cuda.is_available():
                torch.cuda.synchronize()
            t1 = time.time()
            self._infer_time_s += (t1 - t0)

            dets = []
            try:
                r = results[0]
                boxes = r.boxes
                if boxes is not None and len(boxes) > 0:
                    xyxy = boxes.xyxy.cpu().tolist()
                    confs = boxes.conf.cpu().tolist()
                    clss = boxes.cls.cpu().tolist()
                    names = getattr(self.model, "names", {})
                    for i in range(len(confs)):
                        cls_id = int(clss[i])
                        dets.append(
                            {
                                "cls_id": cls_id,
                                "cls_name": names.get(cls_id, str(cls_id)),
                                "conf": float(confs[i]),
                                "xyxy": [float(v) for v in xyxy[i]],
                            }
                        )
            except Exception as e:
                self.log.warning("Failed to parse detections: %s", e)

            self._frames += 1
            now = time.time()
            dt = now - self._last_log
            if dt >= self.info_period:
                fps = self._frames / dt
                avg_ms = (self._infer_time_s / max(1, self._frames)) * 1000.0
                self.log.info(
                    "infer fps: %.1f (avg %.1f ms, last frame_id=%s, dets=%d)",
                    fps,
                    avg_ms,
                    frame_id,
                    len(dets),
                )
                self._frames = 0
                self._infer_time_s = 0.0
                self._last_log = now

            out = {
                "type": "detections",
                "frame_id": frame_id,
                "dets": dets,
            }
            try:
                self.pub_socket.send_json(out, flags=zmq.NOBLOCK)
            except zmq.Again:
                pass


def run():
    DnnWorker().run()
