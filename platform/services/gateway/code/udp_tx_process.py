import os, json, socket, threading, logging
import queue
import zmq
import time

host = os.getenv("ZMQ_CONNECT_SUB_FRAME_META_HOST", "localhost")
port = int(os.getenv("ZMQ_CONNECT_SUB_FRAME_META_PORT", "5562"))
ZMQ_META_SUB = f"tcp://{host}:{port}"

host = os.getenv("ZMQ_CONNECT_SUB_CMD_HOST", "localhost")
port = int(os.getenv("ZMQ_CONNECT_SUB_CMD_PORT", "5561"))
ZMQ_INTERNAL_SUB = f"tcp://{host}:{port}"

host = os.getenv("ZMQ_CONNECT_SUB_RTP_USAGE_HOST", "localhost")
port = int(os.getenv("ZMQ_CONNECT_SUB_RTP_USAGE_PORT", "5563"))
ZMQ_RTP_USAGE_SUB = f"tcp://{host}:{port}"

host = os.getenv("ZMQ_CONNECT_SUB_IMU_HOST", "imu")
port = int(os.getenv("ZMQ_CONNECT_SUB_IMU_PORT", "5530"))
ZMQ_IMU_SUB = f"tcp://{host}:{port}"

host = os.getenv("ZMQ_CONNECT_SUB_TRACKER_HOST", "dnn")
port = int(os.getenv("ZMQ_CONNECT_SUB_TRACKER_PORT", "5580"))
ZMQ_TRACKER_SUB = f"tcp://{host}:{port}"

UDP_META_PORT = int(os.getenv("UDP_META_PORT", "9100"))
UDP_IMU_PORT  = int(os.getenv("UDP_IMU_PORT",  "9101"))
UDP_TELEM_PORT = int(os.getenv("UDP_TELEM_PORT", "9102"))
UDP_TELEM_DESTS = os.getenv("UDP_TELEM_DESTS", "")

LINK_USAGE_HZ = float(os.getenv("LINK_USAGE_HZ", "1"))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("udp_tx")


def run():
    ctx = zmq.Context()

    sub_meta = ctx.socket(zmq.SUB)
    sub_meta.connect(ZMQ_META_SUB)
    sub_meta.setsockopt_string(zmq.SUBSCRIBE, "")

    sub_int = ctx.socket(zmq.SUB)
    sub_int.connect(ZMQ_INTERNAL_SUB)
    sub_int.setsockopt_string(zmq.SUBSCRIBE, "")

    sub_rtp = ctx.socket(zmq.SUB)
    sub_rtp.connect(ZMQ_RTP_USAGE_SUB)
    sub_rtp.setsockopt_string(zmq.SUBSCRIBE, "")

    sub_imu = ctx.socket(zmq.SUB)
    sub_imu.connect(ZMQ_IMU_SUB)
    sub_imu.setsockopt_string(zmq.SUBSCRIBE, "")

    sub_tracker = ctx.socket(zmq.SUB)
    sub_tracker.connect(ZMQ_TRACKER_SUB)
    sub_tracker.setsockopt_string(zmq.SUBSCRIBE, "")

    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_send_q: queue.Queue[tuple[bytes, tuple[str, int]]] = queue.Queue(maxsize=10000)

    # Separate sink sets so enabling RTP/meta does NOT implicitly enable IMU.
    dests_meta = set()    # {(ip, port)} for meta/link-usage/etc (UDP_META_PORT)
    dests_imu  = set()    # {(ip, port)} for IMU (UDP_IMU_PORT)

    dests_lock = threading.Lock()


    # accounting
    usage_lock = threading.Lock()
    udp_bytes = 0
    latest_rtp = {"bps": 0, "bytes": 0, "dt_s": 0.0, "sinks_ok": 0, "sinks_total": 0}

    def _parse_telem_dests(s: str):
        out = []
        for part in (s or "").split(","):
            p = part.strip()
            if not p:
                continue
            if ":" in p:
                ip, port_s = p.rsplit(":", 1)
                try:
                    port_i = int(port_s)
                except ValueError:
                    continue
            else:
                ip = p
                port_i = UDP_TELEM_PORT
            out.append((ip, port_i))
        return out

    telem_dests = _parse_telem_dests(UDP_TELEM_DESTS)

    def _udp_add_bytes(n: int):
        nonlocal udp_bytes
        with usage_lock:
            udp_bytes += int(n)

    def udp_sender_loop():
        while True:
            payload, target = udp_send_q.get()
            udp.sendto(payload, target)
            _udp_add_bytes(len(payload))

    def rtp_usage_loop():
        nonlocal latest_rtp
        while True:
            msg = sub_rtp.recv_json()
            if msg.get("type") == "RTP_USAGE":
                with usage_lock:
                    latest_rtp = msg.get("value", {}) or latest_rtp

    def usage_report_loop():
        nonlocal udp_bytes
        period = 1.0 / max(0.1, LINK_USAGE_HZ)
        last = time.monotonic()
        while True:
            time.sleep(period)
            now = time.monotonic()
            dt = now - last
            last = now

            with usage_lock:
                b = udp_bytes
                udp_bytes = 0
                rtp = dict(latest_rtp)

            udp_bps = int((b * 8) / dt) if dt > 0 else 0
            out = {
                "type": "LINK_USAGE",
                "value": {
                    "udp_bps": int(udp_bps),
                    "udp_bytes": int(b),
                    "rtp_bps": int(rtp.get("bps", 0) or 0),
                    "rtp_bytes": int(rtp.get("bytes", 0) or 0),
                    "rtp_sinks_ok": int(rtp.get("sinks_ok", 0) or 0),
                    "rtp_sinks_total": int(rtp.get("sinks_total", 0) or 0),
                    "dt_s": float(dt),
                },
            }
            payload = json.dumps(out).encode("utf-8")

            targets = list(telem_dests)
            for (ip, port) in targets:
                udp_send_q.put((payload, (ip, port)))

    def internal_loop():
        while True:
            cmd = sub_int.recv_json()
            ctype = cmd.get("type")
            ip = cmd.get("ip")
            if not ip:
                continue

            # Existing: RTP request enables META sink (not IMU).
            if ctype == "RTP_ADD_SINK":
                with dests_lock:
                    dests_meta.add((ip, UDP_META_PORT))
                log.info("Added META sink %s:%d (via RTP_ADD_SINK)", ip, UDP_META_PORT)

            # Optional symmetry for toggles
            elif ctype == "RTP_REMOVE_SINK":
                with dests_lock:
                    dests_meta.discard((ip, UDP_META_PORT))
                log.info("Removed META sink %s:%d (via RTP_REMOVE_SINK)", ip, UDP_META_PORT)

            # New: explicit IMU gating
            elif ctype == "IMU_ADD_SINK":
                with dests_lock:
                    dests_imu.add((ip, UDP_IMU_PORT))
                log.info("Added IMU sink %s:%d (via IMU_ADD_SINK)", ip, UDP_IMU_PORT)

            elif ctype == "IMU_REMOVE_SINK":
                with dests_lock:
                    dests_imu.discard((ip, UDP_IMU_PORT))
                log.info("Removed IMU sink %s:%d (via IMU_REMOVE_SINK)", ip, UDP_IMU_PORT)
 

    def meta_loop():
        while True:
            meta = sub_meta.recv_json()
            payload = json.dumps(meta).encode("utf-8")
            with dests_lock:
                targets = list(dests_meta)
            for (ip, port) in targets:
                udp_send_q.put((payload, (ip, port)))

    def imu_loop():
        """
        Drain IMU ZMQ stream continuously.
        Only UDP-send when IMU sinks exist.
        IMPORTANT: UDP payload must be pure JSON bytes (client udp_rx does json.loads(data)).
        """
        while True:
            parts = sub_imu.recv_multipart()
            payload = parts[-1]  # JSON bytes from run_imu.py PUB

            with dests_lock:
                targets = list(dests_imu)
            if not targets:
                continue

            for (ip, port) in targets:
                udp_send_q.put((payload, (ip, port)))

    def tracker_status_loop():
        while True:
            msg = sub_tracker.recv_json()
            payload = json.dumps(msg).encode("utf-8")
            for (ip, port) in list(telem_dests):
                udp_send_q.put((payload, (ip, port)))


    threading.Thread(target =   udp_sender_loop, daemon=True).start()
    threading.Thread(target =     internal_loop, daemon=True).start()
    threading.Thread(target =    rtp_usage_loop, daemon=True).start()
    threading.Thread(target = usage_report_loop, daemon=True).start()
    threading.Thread(target =         imu_loop, daemon=True).start()
    threading.Thread(target=tracker_status_loop, daemon=True).start()

    log.info("UDP meta TX online (internal thread started)")

    meta_loop()  # run in main thread
