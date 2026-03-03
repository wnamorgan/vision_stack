# This file would handle the received UDP messages
# For example, mapping the message to actions like controlling platform components.

import os
import zmq
import logging
import threading
import time

host = os.getenv("ZMQ_CONNECT_SUB_INTENT_HOST", "localhost")
port = int(os.getenv("ZMQ_CONNECT_SUB_INTENT_PORT", "5560"))
ZMQ_INTENT_SUB = f"tcp://{host}:{port}"
host = os.getenv("ZMQ_BIND_PUB_CMD_HOST", "0.0.0.0")
port = int(os.getenv("ZMQ_BIND_PUB_CMD_PORT", "5561"))
ZMQ_INTERNAL_PUB = f"tcp://{host}:{port}"
GW_HEARTBEAT_HZ = float(os.getenv("GW_HEARTBEAT_HZ", "1.0"))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("control")

def run():
    ctx = zmq.Context()

    sub = ctx.socket(zmq.SUB)
    sub.connect(ZMQ_INTENT_SUB)
    sub.setsockopt_string(zmq.SUBSCRIBE, "")

    pub = ctx.socket(zmq.PUB)
    pub.bind(ZMQ_INTERNAL_PUB)

    frame_endpoint = {"value": None}
    log.info("Control handler online")

    reg_lock = threading.Lock()
    registered_endpoints = set()

    def heartbeat_loop():
        period = 1.0 / max(0.1, GW_HEARTBEAT_HZ)
        while True:
            time.sleep(period)
            with reg_lock:
                endpoints = sorted(registered_endpoints)
            pub.send_json({
                "type": "GW_HEARTBEAT",
                "value": {
                    "registered_endpoints": endpoints,
                    "ts": time.time(),
                },
            })

    threading.Thread(target=heartbeat_loop, daemon=True).start()

    while True:
        intent = sub.recv_json()
        if intent.get("type") == "RTP_SUBSCRIBE":
            cmd = {
                "type": "RTP_ADD_SINK",
                "ip": intent["value"]["ip"],
                "port": int(intent["value"]["port"]),
            }
            pub.send_json(cmd)
        elif intent.get("type") == "RTP_UNSUBSCRIBE":
            cmd = {
                "type": "RTP_REMOVE_SINK",
                "ip": intent["value"]["ip"],
                "port": int(intent["value"]["port"]),
            }
            pub.send_json(cmd)
        elif intent.get("type") == "GW_REGISTER_ZMQ_SUB":
            endpoint = None
            if isinstance(intent.get("value"), dict):
                endpoint = intent["value"].get("endpoint")
            if endpoint:
                with reg_lock:
                    registered_endpoints.add(endpoint)
            pub.send_json(intent)
        elif intent.get("type") == "GW_REGISTER_FRAME_ZMQ_SUB":
            endpoint = None
            if isinstance(intent.get("value"), dict):
                endpoint = intent["value"].get("endpoint")
            if endpoint:
                with reg_lock:
                    registered_endpoints.add(endpoint)
                frame_endpoint["value"] = endpoint
                pub.send_json({"type": "RTP_SET_FRAME_SOURCE", "value": {"endpoint": endpoint}})
            pub.send_json(intent)
        elif str(intent.get("type", "")).endswith(("_ADD_SINK", "_REMOVE_SINK")):
            # pass through generic sink control intents to internal bus
            pub.send_json(intent)
        elif intent.get("type") == "RTP_SET_PARAMS":
            # pass through; HostRTP will clamp and apply
            pub.send_json({
                "type": "RTP_SET_PARAMS",
                "value": intent.get("value", {}),
            })
