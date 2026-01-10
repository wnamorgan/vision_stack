import os
import time
import cv2
import numpy as np
import threading
import queue
import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst

from multiprocessing import shared_memory
from multiprocessing import resource_tracker

import zmq
import logging


# ---- defaults (initial) ----
DEFAULT_W = int(os.getenv("RTP_WIDTH", "1280"))
DEFAULT_H = int(os.getenv("RTP_HEIGHT", "720"))
DEFAULT_Q = int(os.getenv("RTP_QUALITY", os.getenv("RTP_JPEG_QUALITY", "80")))
DEFAULT_F = float(os.getenv("RTP_TX_HZ", "30"))


ZMQ_RTP_USAGE_PUB  = f"tcp://*:{int(os.getenv('ZMQ_RTP_USAGE_PORT'))}"

ZMQ_SUB_ENDPOINT = os.getenv("ZMQ_SUB_ENDPOINT", "tcp://localhost:5555")
ZMQ_FRAME_META_PUB = os.getenv("ZMQ_FRAME_META_PUB", "tcp://*:5562")

RTP_PORT = int(os.getenv("RTP_PORT", "5004"))
RTP_DST_IP = os.getenv("RTP_DST_IP", "127.0.0.1")

LINK_USAGE_HZ = float(os.getenv("LINK_USAGE_HZ", "1"))

class HostRTP:
    def __init__(self):
        # bounds for SHM buffer (matches your current approach)
        self.MAX_HEIGHT = 4320
        self.MAX_WIDTH = 7680

        self.shm = None
        self.image_buf = None

        # queues: keep latest only
        self.frame_queue = queue.Queue(maxsize=1)  # latest frame from ZMQ ingest
        self.tx_queue = queue.Queue(maxsize=1)     # paced sender input

        self.stop_event = threading.Event()

        # logging
        self.log = logging.getLogger("HostRTP")
        logging.basicConfig(level=logging.INFO)

        # runtime settings (mutable)
        self.out_w = DEFAULT_W
        self.out_h = DEFAULT_H
        self.Tx_Hz = DEFAULT_F

        self._q_lock = threading.Lock()
        self.jpeg_quality = DEFAULT_Q

        # RTP sinks
        self.sink_lock = threading.Lock()
        self.rtp_sinks = {}

        # ZMQ
        self.context = zmq.Context()
        self.sub_socket = self.context.socket(zmq.SUB)
        self.sub_socket.connect(ZMQ_SUB_ENDPOINT)
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")
        self.sub_socket.RCVTIMEO = 200  # ms


        # RTP usage publisher (dedicated channel)
        self.usage_pub = self.context.socket(zmq.PUB)
        self.usage_pub.setsockopt(zmq.SNDHWM, 1)
        self.usage_pub.setsockopt(zmq.LINGER, 0)
        self.usage_pub.bind(ZMQ_RTP_USAGE_PUB)
 
        # RTP byte accounting (true bytes pushed to sinks)
        self._usage_lock = threading.Lock()
        self._rtp_bytes = 0
        self._rtp_sinks_ok = 0
        self._rtp_sinks_total = 0


        # Side-channel publisher (frame metadata)
        self.meta_pub = self.context.socket(zmq.PUB)
        self.meta_pub.setsockopt(zmq.SNDHWM, 1)  # keep only latest if congested
        self.meta_pub.setsockopt(zmq.LINGER, 0)
        self.meta_pub.bind(ZMQ_FRAME_META_PUB)

        # GStreamer init
        Gst.init(None)

        # application frame_id (local counter)
        self.frame_id = 0

        # initial sink
        self._add_rtp_sink(RTP_DST_IP, RTP_PORT)

    # ----------------------------
    # Public controls
    # ----------------------------
    def set_jpeg_quality(self, q: int):
        q = max(10, min(95, int(q)))
        with self._q_lock:
            self.jpeg_quality = q
        self.log.info("[RTP] JPEG quality set to %d", q)

    def apply_rtp_params(self, p: dict):
        """
        Apply runtime parameters coming from control plane.
        Expected keys (any subset): quality, fps, w, h.
        - quality/fps update in-place
        - w/h changes require rebuilding sink pipelines (caps change)
        """
        try:
            old_w, old_h = self.out_w, self.out_h
            old_q = self.jpeg_quality
            old_hz = self.Tx_Hz

            changed_size = False

            if "quality" in p:
                self.set_jpeg_quality(int(p["quality"]))

            if "fps" in p:
                hz = float(p["fps"])
                # clamp: allow diagnostic high rates but prevent div-by-zero / nonsense
                self.Tx_Hz = max(0.1, min(240.0, hz))

            if "w" in p:
                nw = max(64, int(p["w"]))
                if nw != self.out_w:
                    self.out_w = nw
                    changed_size = True

            if "h" in p:
                nh = max(64, int(p["h"]))
                if nh != self.out_h:
                    self.out_h = nh
                    changed_size = True

            if changed_size:
                self.log.info(
                    "[RTP] Size change %dx%d -> %dx%d; rebuilding sinks",
                    old_w, old_h, self.out_w, self.out_h
                )
                self._rebuild_all_sinks()
            else:
                # Explicitly do NOT touch pipelines for quality/fps-only changes
                self.log.info(
                    "[RTP] No size change; not rebuilding sinks (q %d->%d, hz %.1f->%.1f)",
                    old_q, self.jpeg_quality, old_hz, self.Tx_Hz
                )

        except Exception as e:
            self.log.warning("[RTP] Failed applying params %s (%s)", p, e)

    # ----------------------------
    # Main runner
    # ----------------------------
    def run(self):
        zmq_thread = threading.Thread(target=self.zmq_sub_loop, daemon=True)
        process_thread = threading.Thread(target=self.process_frames, daemon=True)
        tx_thread = threading.Thread(target=self.tx_rate_loop, daemon=True)
        usage_thread = threading.Thread(target=self._rtp_usage_report_loop, daemon=True)

        zmq_thread.start()
        process_thread.start()
        tx_thread.start()
        usage_thread.start()

        try:
            while not self.stop_event.is_set():
                time.sleep(0.2)
        finally:
            self.stop_event.set()

            # best-effort join
            zmq_thread.join(timeout=1.0)
            process_thread.join(timeout=1.0)
            tx_thread.join(timeout=1.0)

            # teardown sinks
            with self.sink_lock:
                sinks = list(self.rtp_sinks.items())
                self.rtp_sinks = {}

            for (ip, port), (pipeline, appsrc) in sinks:
                try:
                    appsrc.emit("end-of-stream")
                except Exception:
                    pass
                pipeline.set_state(Gst.State.NULL)

            # SHM
            try:
                if self.shm is not None:
                    self.shm.close()
            except Exception:
                pass

            # ZMQ
            try:
                self.sub_socket.close()
            except Exception:
                pass
            try:
                self.meta_pub.close()
            except Exception:
                pass
            try:
                self.usage_pub.close()
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
        metadata = msg["metadata"]
        width = int(metadata["w"])
        height = int(metadata["h"])
        channels = int(metadata["c"])

        # first frame: attach to SHM
        if self.shm is None:
            self.shm = shared_memory.SharedMemory(name=shm_name)
            resource_tracker.unregister(self.shm._name, "shared_memory")
            self.image_buf = np.ndarray(
                (self.MAX_HEIGHT, self.MAX_WIDTH, channels),
                dtype=np.uint8,
                buffer=self.shm.buf[: self.MAX_WIDTH * self.MAX_HEIGHT * channels],
            )

        # copy semantics preserved
        image = self.image_buf[:height, :width, :channels].copy()

        self.frame_id += 1
        frame = (image, msg, self.frame_id)

        if self.frame_id % 1000 == 0:
            self.log.info("[RTP] Frame Count = %d", self.frame_id)

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
    # TX pacing loop
    # ----------------------------
    def tx_rate_loop(self):
        next_tx = time.time()

        while not self.stop_event.is_set():
            hz = float(self.Tx_Hz)
            period = 1.0 / max(0.1, hz)

            now = time.time()
            if now < next_tx:
                time.sleep(next_tx - now)
            next_tx += period

            try:
                frame = self.frame_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                self.tx_queue.put_nowait(frame)
            except queue.Full:
                try:
                    self.tx_queue.get_nowait()
                except queue.Empty:
                    pass
                self.tx_queue.put_nowait(frame)

    # ----------------------------
    # Encode + send
    # ----------------------------
    def process_frames(self):
        count = 0
        last = time.time()
        fps = None

        while not self.stop_event.is_set():
            try:
                frame_bgr, msg, frame_id = self.tx_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            # publish metadata (already includes frame_id if you put it there upstream)
            try:
                self.meta_pub.send_json(
                    {"type": "FRAME_META", "value": msg["metadata"]},
                    flags=zmq.NOBLOCK,
                )
            except zmq.Again:
                pass

            # resize to current output size
            frame = cv2.resize(frame_bgr, (self.out_w, self.out_h), interpolation=cv2.INTER_LINEAR)

            # compute/debug FPS
            count += 1
            now = time.time()
            if now - last >= 1.0:
                fps = count / (now - last)
                self.log.info("[TX] FPS=%.1f", fps)
                count = 0
                last = now

            # optional overlay
            if fps:
                cv2.putText(
                    frame,
                    f"FPS: {fps:.1f}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA,
                )

            with self._q_lock:
                q = int(self.jpeg_quality)

            ok, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), q])
            if not ok:
                continue

            data = jpg.tobytes()
            data_len = len(data)
            buf = Gst.Buffer.new_allocate(None, len(data), None)
            buf.fill(0, data)

            # push to sinks
            dead_sinks = []
            with self.sink_lock:
                items = list(self.rtp_sinks.items())
            sinks_ok = 0
            for (ip, port), (pipeline, appsrc) in items:          
                flow = appsrc.emit("push-buffer", buf)
                if flow != Gst.FlowReturn.OK:
                    self.log.warning("RTP sink %s:%d push-buffer failed (%s), removing", ip, port, flow)
                    dead_sinks.append((ip, port))
                else:
                    sinks_ok+=1

            # bytes actually sent (per-sink)
            if sinks_ok and data_len:
                self._usage_add_rtp(data_len * sinks_ok, sinks_ok, len(items))

            if dead_sinks:
                with self.sink_lock:
                    for key in dead_sinks:
                        pipeline, appsrc = self.rtp_sinks.pop(key, (None, None))
                        if pipeline is None:
                            continue
                        try:
                            appsrc.emit("end-of-stream")
                        except Exception:
                            pass
                        pipeline.set_state(Gst.State.NULL)

            if not self.rtp_sinks:
                self.log.warning("No RTP sinks remain")

    # ----------------------------
    # Sink management
    # ----------------------------
    def _add_rtp_sink(self, ip: str, port: int):
        with self.sink_lock:
            if (ip, port) in self.rtp_sinks:
                self.log.info("RTP sink %s:%d already exists, ignoring", ip, port)
                return

        self.log.info("Adding RTP sink %s:%d", ip, port)

        pipeline_str = (
            f"appsrc name=src is-live=true block=false format=time do-timestamp=true "
            f"caps=image/jpeg,width={self.out_w},height={self.out_h} ! "
            f"rtpjpegpay pt=26 ! "
            f"udpsink host={ip} port={port} sync=false async=false"
        )

        pipeline = Gst.parse_launch(pipeline_str)
        appsrc = pipeline.get_by_name("src")
        pipeline.set_state(Gst.State.PLAYING)

        with self.sink_lock:
            self.rtp_sinks[(ip, port)] = (pipeline, appsrc)

    def _rebuild_all_sinks(self):
        # capture destinations + teardown old pipelines
        with self.sink_lock:
            dests = list(self.rtp_sinks.keys())
            old = self.rtp_sinks
            self.rtp_sinks = {}

        for (ip, port), (pipeline, appsrc) in old.items():
            try:
                appsrc.emit("end-of-stream")
            except Exception:
                pass
            pipeline.set_state(Gst.State.NULL)

        # recreate with updated caps
        for ip, port in dests:
            self._add_rtp_sink(ip, port)

    def _usage_add_rtp(self, bytes_sent: int, sinks_ok: int, sinks_total: int):
        with self._usage_lock:
            self._rtp_bytes += int(bytes_sent)
            self._rtp_sinks_ok = int(sinks_ok)
            self._rtp_sinks_total = int(sinks_total)
 
    def _rtp_usage_report_loop(self):
        period = 1.0 / max(0.1, LINK_USAGE_HZ)
        last = time.monotonic()
        while not self.stop_event.is_set():
            time.sleep(period)
            now = time.monotonic()
            dt = now - last
            last = now
 
            with self._usage_lock:
                b = self._rtp_bytes
                ok = self._rtp_sinks_ok
                total = self._rtp_sinks_total
                self._rtp_bytes = 0
 
            bps = int((b * 8) / dt) if dt > 0 else 0
            msg = {
                "type": "RTP_USAGE",
                "value": {
                    "bps": bps,
                    "bytes": int(b),
                    "dt_s": float(dt),
                    "sinks_ok": int(ok),
                    "sinks_total": int(total),
                },
            }
            try:
                self.usage_pub.send_json(msg, flags=zmq.NOBLOCK)
            except zmq.Again:
                pass
 

# Gstreamer works from linux as source
# gst-launch-1.0 -v   v4l2src device=/dev/video0 !   image/jpeg,framerate=120/1 !   rtpjpegpay pt=26 !   udpsink host=127.0.0.1 port=5004 sync=false async=false
