import os, json, socket, threading, logging
import zmq
import time

ZMQ_META_SUB = os.getenv("ZMQ_META_SUB", "tcp://localhost:5562")
ZMQ_INTERNAL_SUB = os.getenv("ZMQ_INTERNAL_SUB", "tcp://localhost:5561")
META_UDP_PORT = int(os.getenv("META_UDP_PORT", "9100"))
ZMQ_RTP_USAGE_SUB = f"tcp://localhost:{int(os.getenv("ZMQ_RTP_USAGE_PORT"))}"
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


    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    dests = set()         # {(ip, port)}
    dests_lock = threading.Lock()


    # accounting
    usage_lock = threading.Lock()
    udp_bytes = 0
    latest_rtp = {"bps": 0, "bytes": 0, "dt_s": 0.0, "sinks_ok": 0, "sinks_total": 0}

    def _udp_add_bytes(n: int):
        nonlocal udp_bytes
        with usage_lock:
            udp_bytes += int(n)

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

            with dests_lock:
                targets = list(dests)
            for (ip, port) in targets:
                udp.sendto(payload, (ip, port))
                _udp_add_bytes(len(payload))


    def internal_loop():
        while True:
            cmd = sub_int.recv_json()
            if cmd.get("type") == "RTP_ADD_SINK":
                ip = cmd.get("ip")
                if ip:
                    with dests_lock:
                        dests.add((ip, META_UDP_PORT))
                    log.info("Added meta dest %s:%d", ip, META_UDP_PORT)

    def meta_loop():
        while True:
            meta = sub_meta.recv_json()
            payload = json.dumps(meta).encode("utf-8")
            with dests_lock:
                targets = list(dests)
            for (ip, port) in targets:
                udp.sendto(payload, (ip, port))

    threading.Thread(target =     internal_loop, daemon=True).start()
    threading.Thread(target =    rtp_usage_loop, daemon=True).start()
    threading.Thread(target = usage_report_loop, daemon=True).start()

    log.info("UDP meta TX online (internal thread started)")

    meta_loop()  # run in main thread
