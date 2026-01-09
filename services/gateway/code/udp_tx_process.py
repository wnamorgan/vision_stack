import os, json, socket, threading, logging
import zmq

ZMQ_META_SUB = os.getenv("ZMQ_META_SUB", "tcp://localhost:5562")
ZMQ_INTERNAL_SUB = os.getenv("ZMQ_INTERNAL_SUB", "tcp://localhost:5561")
META_UDP_PORT = int(os.getenv("META_UDP_PORT", "9100"))

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

    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    dests = set()         # {(ip, port)}
    dests_lock = threading.Lock()

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

    threading.Thread(target=internal_loop, daemon=True).start()
    log.info("UDP meta TX online (internal thread started)")

    meta_loop()  # run in main thread
