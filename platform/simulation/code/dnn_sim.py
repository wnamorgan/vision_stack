import os
import time
import logging
import threading
import queue

import zmq


def _env_float(name, default):
    value = os.getenv(name)
    return float(value) if value else default


class DnnSim:
    def __init__(self):
        self.stop_event = None
        self.frame_queue = queue.Queue(maxsize=1)
        self.preproc_queue = queue.Queue(maxsize=1)

        self.cls_id = int(os.getenv("SIM_DET_CLASS_ID", "0"))
        self.cls_name = os.getenv("SIM_DET_CLASS_NAME", "target")
        self.conf = _env_float("SIM_DET_CONF", 0.9)
        self.info_period = _env_float("INFO_PERIOD", 10.0)

        logging.basicConfig(
            level=os.getenv("LOG_LEVEL", "INFO"),
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
        self.log = logging.getLogger("dnn_sim")

        self.context = zmq.Context.instance()
        self.sub_socket = self.context.socket(zmq.SUB)
        cam_ep = (
            f"tcp://{os.getenv('ZMQ_CONNECT_SUB_CAMERA_HOST','localhost')}:"
            f"{os.getenv('ZMQ_CONNECT_SUB_CAMERA_PORT','5555')}"
        )
        self.sub_socket.connect(cam_ep)
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")
        self.sub_socket.RCVTIMEO = 200

        self.pub_socket = self.context.socket(zmq.PUB)
        det_ep = (
            f"tcp://{os.getenv('ZMQ_BIND_PUB_DET_HOST','0.0.0.0')}:"
            f"{os.getenv('ZMQ_BIND_PUB_DET_PORT','5566')}"
        )
        self.pub_socket.bind(det_ep)

        self._last_log = time.time()
        self._frames = 0

        self.log.info("DNN ZMQ SUB connected: %s", cam_ep)
        self.log.info("DNN ZMQ PUB bound: %s", det_ep)
        self.log.info(
            "SIM_DET_CLASS_ID=%s SIM_DET_CLASS_NAME=%s SIM_DET_CONF=%s",
            self.cls_id,
            self.cls_name,
            self.conf,
        )

    def enqueue_frame(self, msg: dict):
        md = msg.get("metadata", {})
        frame_id = md.get("frame_id")
        if frame_id is None:
            return
        frame = (msg, frame_id)
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

    def preprocess_loop(self):
        while not self.stop_event.is_set():
            try:
                frame = self.frame_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self.preproc_queue.put_nowait(frame)
            except queue.Full:
                try:
                    self.preproc_queue.get_nowait()
                except queue.Empty:
                    pass
                self.preproc_queue.put_nowait(frame)

    def infer_loop(self):
        while not self.stop_event.is_set():
            try:
                msg, frame_id = self.preproc_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            md = msg.get("metadata") or {}
            dets = [{
                "cls_id": self.cls_id,
                "cls_name": self.cls_name,
                "conf": self.conf,
                "xyxy": [100.0, 100.0, 200.0, 200.0],
            }]
            out = {
                "type": "detections",
                "frame_id": frame_id,
                "t_cam_hw_ns": md.get("t_cam_hw_ns"),
                "t_cam_sw_ns": md.get("t_cam_sw_ns"),
                "dets": dets,
            }
            try:
                self.pub_socket.send_json(out, flags=zmq.NOBLOCK)
            except zmq.Again:
                pass

            self._frames += 1
            now = time.time()
            dt = now - self._last_log
            if dt >= self.info_period:
                fps = self._frames / dt
                self.log.info("publishing ~%.1f Hz", fps)
                self._frames = 0
                self._last_log = now

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


def dnn_loop(stop_event):
    sim = DnnSim()
    sim.stop_event = stop_event
    sim.run()
