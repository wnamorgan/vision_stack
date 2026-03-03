import os
import time
import threading
import zmq
import logging

ZMQ_BIND_PULL_CLIENT_GW_CMD_HOST = os.getenv("ZMQ_BIND_PULL_CLIENT_GW_CMD_HOST", "0.0.0.0")
ZMQ_BIND_PULL_CLIENT_GW_CMD_PORT = int(os.getenv("ZMQ_BIND_PULL_CLIENT_GW_CMD_PORT", "6010"))
ZMQ_PULL_ENDPOINT = f"tcp://{ZMQ_BIND_PULL_CLIENT_GW_CMD_HOST}:{ZMQ_BIND_PULL_CLIENT_GW_CMD_PORT}"

ZMQ_BIND_PUB_CLIENT_GW_CMD_HOST = os.getenv("ZMQ_BIND_PUB_CLIENT_GW_CMD_HOST", "0.0.0.0")
ZMQ_BIND_PUB_CLIENT_GW_CMD_PORT = int(os.getenv("ZMQ_BIND_PUB_CLIENT_GW_CMD_PORT", "5575"))
ZMQ_PUB_ENDPOINT = f"tcp://{ZMQ_BIND_PUB_CLIENT_GW_CMD_HOST}:{ZMQ_BIND_PUB_CLIENT_GW_CMD_PORT}"

GW_HEARTBEAT_HZ = float(os.getenv("GW_HEARTBEAT_HZ", "1.0"))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("client_control")


def run():
    ctx = zmq.Context()
    pull = ctx.socket(zmq.PULL)
    pull.bind(ZMQ_PULL_ENDPOINT)

    pub = ctx.socket(zmq.PUB)
    pub.bind(ZMQ_PUB_ENDPOINT)

    reg_lock = threading.Lock()
    registered_udp = set()  # {(name, port)}

    def heartbeat_loop():
        period = 1.0 / max(0.1, GW_HEARTBEAT_HZ)
        while True:
            time.sleep(period)
            with reg_lock:
                regs = sorted(
                    [{"name": n, "port": p} for (n, p) in registered_udp],
                    key=lambda x: (x["name"], x["port"]),
                )
            pub.send_json({"type": "GW_HEARTBEAT", "value": {"udp_bindings": regs, "ts": time.time()}})

    threading.Thread(target=heartbeat_loop, daemon=True).start()
    log.info("Client gateway control handler online")

    while True:
        msg = pull.recv_json()
        if msg.get("type") == "GW_REGISTER_UDP_BIND":
            val = msg.get("value") or {}
            name = val.get("name")
            port = val.get("port")
            if name and isinstance(port, int):
                with reg_lock:
                    registered_udp.add((name, port))
            pub.send_json(msg)  # pass-through for udp_rx_process
