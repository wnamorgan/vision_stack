import os
import time
import logging
from multiprocessing import shared_memory
import zmq
import numpy as np

import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("rtp_rx_shm")


def _env_int(key: str, default: int) -> int:
    v = os.getenv(key)
    return int(v) if v is not None and v != "" else default

RTP_RX_LISTEN_PORT = _env_int("RTP_RX_LISTEN_PORT", 5004)

SHM_NAME = os.getenv("RTP_RX_SHM_NAME", "client_rtp_rx_shm")

# Allocate big enough for worst-case JPEG payload.
# Pick something sane; 8–16MB is typical for high-res JPEGs depending on quality.
MAX_JPEG_BYTES = _env_int("MAX_JPEG_BYTES", 16 * 1024 * 1024)

META_BYTES = 32

ZMQ_FRAME_PUB = os.getenv("ZMQ_FRAME_PUB", "tcp://*:5572")
def _make_frame_pub():
    ctx = zmq.Context.instance()
    pub = ctx.socket(zmq.PUB)
    pub.setsockopt(zmq.LINGER, 0)
    # keep it small; latest update only
    pub.setsockopt(zmq.SNDHWM, int(os.getenv("ZMQ_SNDHWM", "10")))
    pub.bind(ZMQ_FRAME_PUB)
    return pub



class ShmJpegWriter:
    """
    SHM layout:
      [0 : MAX_JPEG_BYTES)                 = uint8 JPEG bytes (valid [0:nbytes])
      [MAX_JPEG_BYTES : +8)                = uint64 seq
      [MAX_JPEG_BYTES + 8 : +12)           = uint32 nbytes
      [MAX_JPEG_BYTES + 12 : +20)          = uint64 host_time_ns
      remaining reserved
    """

    def __init__(self, name: str, max_bytes: int):
        self.name = name
        self.max_bytes = max_bytes
        self.size = self.max_bytes + META_BYTES

        self.shm: shared_memory.SharedMemory | None = None
        self.buf: np.ndarray | None = None
        self.seq: np.ndarray | None = None
        self.nbytes: np.ndarray | None = None
        self.host_time_ns: np.ndarray | None = None

    def create(self) -> None:
        # Recreate if exists (same pattern you use elsewhere)
        try:
            old = shared_memory.SharedMemory(name=self.name)
            old.unlink()
            old.close()
        except FileNotFoundError:
            pass

        self.shm = shared_memory.SharedMemory(create=True, name=self.name, size=self.size)
        b = self.shm.buf

        self.buf = np.ndarray((self.max_bytes,), dtype=np.uint8, buffer=b[: self.max_bytes])

        meta_off = self.max_bytes
        self.seq = np.ndarray((1,), dtype=np.uint64, buffer=b, offset=meta_off)
        self.nbytes = np.ndarray((1,), dtype=np.uint32, buffer=b, offset=meta_off + 8)
        self.host_time_ns = np.ndarray((1,), dtype=np.uint64, buffer=b, offset=meta_off + 12)

        self.seq[0] = 0
        self.nbytes[0] = 0
        self.host_time_ns[0] = 0

        log.info("[SHM] created name=%s size=%d max_bytes=%d", self.name, self.size, self.max_bytes)

    def write(self, jpeg_bytes: bytes) -> None:
        n = len(jpeg_bytes)
        if n > self.max_bytes:
            # Don’t corrupt SHM; drop and warn.
            log.warning("[SHM] drop frame: jpeg bytes=%d exceeds MAX_JPEG_BYTES=%d", n, self.max_bytes)
            return

        # odd/even seq pattern
        self.seq[0] += 1  # odd = write in progress
        self.nbytes[0] = n
        self.host_time_ns[0] = time.time_ns()

        # copy payload
        self.buf[:n] = np.frombuffer(jpeg_bytes, dtype=np.uint8)

        self.seq[0] += 1  # even = write complete


def run() -> None:
    Gst.init(None)

    frame_pub = _make_frame_pub()

    writer = ShmJpegWriter(SHM_NAME, MAX_JPEG_BYTES)
    writer.create()

    # Mirror GCS video_process intent: rtpjpegdepay -> appsink (NO decode/encode)
    pipeline_str = (
        f'udpsrc port={RTP_RX_LISTEN_PORT} caps="application/x-rtp,media=video,encoding-name=JPEG,payload=26,clock-rate=90000" '
        f'! rtpjitterbuffer latency=0 '
        f'! rtpjpegdepay '
        f'! appsink name=sink caps=image/jpeg sync=false max-buffers=1 drop=true'
    )

    log.info("[RTP->SHM] starting pipeline port=%d -> shm=%s", RTP_RX_LISTEN_PORT, SHM_NAME)
    pipe = Gst.parse_launch(pipeline_str)
    sink = pipe.get_by_name("sink")
    pipe.set_state(Gst.State.PLAYING)

    bus = pipe.get_bus()
    frames = 0
    t0 = time.time()

    while True:
        # Pull samples without requiring a GLib main loop.
        sample = sink.emit("try-pull-sample", 100_000_000)  # 0.1s in ns
        if sample is not None:
            buf = sample.get_buffer()
            ok, mapinfo = buf.map(Gst.MapFlags.READ)
            if ok:
                jpeg_bytes = bytes(mapinfo.data)
                writer.write(jpeg_bytes)
                buf.unmap(mapinfo)
                frames += 1

            # Notify services that SHM has a new frame
            msg = {
                "type": "GCS_FRAME_SHM",
                "value": {
                    "shm_name": SHM_NAME,
                    "nbytes": int(len(jpeg_bytes)),
                    "t_host": time.time(),
                },
            }
            try:
                frame_pub.send_json(msg, flags=zmq.NOBLOCK)
            except zmq.Again:
                pass

        now = time.time()
        if now - t0 >= 10.0:
            seq = int(writer.seq[0])
            nb = int(writer.nbytes[0])
            log.info("[RTP->SHM] port=%d fps=%d seq=%d nbytes=%d", RTP_RX_LISTEN_PORT, frames, seq, nb)
            frames = 0
            t0 = now

        msg = bus.timed_pop_filtered(0, Gst.MessageType.ERROR | Gst.MessageType.EOS)
        if msg:
            if msg.type == Gst.MessageType.ERROR:
                err, dbg = msg.parse_error()
                log.error("[RTP->SHM] GST ERROR: %s dbg=%s", err, dbg)
                break
            if msg.type == Gst.MessageType.EOS:
                log.warning("[RTP->SHM] EOS")
                break

    pipe.set_state(Gst.State.NULL)
