# This file would handle the received UDP messages
# For example, mapping the message to actions like controlling platform components.

import os
import zmq
import logging

host = os.getenv("ZMQ_CONNECT_SUB_INTENT_HOST", "localhost")
port = int(os.getenv("ZMQ_CONNECT_SUB_INTENT_PORT", "5560"))
ZMQ_INTENT_SUB = f"tcp://{host}:{port}"
host = os.getenv("ZMQ_BIND_PUB_CMD_HOST", "0.0.0.0")
port = int(os.getenv("ZMQ_BIND_PUB_CMD_PORT", "5561"))
ZMQ_INTERNAL_PUB = f"tcp://{host}:{port}"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("control")

def run():
    ctx = zmq.Context()

    sub = ctx.socket(zmq.SUB)
    sub.connect(ZMQ_INTENT_SUB)
    sub.setsockopt_string(zmq.SUBSCRIBE, "")

    pub = ctx.socket(zmq.PUB)
    pub.bind(ZMQ_INTERNAL_PUB)

    log.info("Control handler online")

    while True:
        intent = sub.recv_json()
        if intent.get("type") == "RTP_SUBSCRIBE":
            cmd = {
                "type": "RTP_ADD_SINK",
                "ip": intent["value"]["ip"],
                "port": int(intent["value"]["port"]),
            }
            pub.send_json(cmd)
        elif intent.get("type") in ("IMU_ADD_SINK", "IMU_REMOVE_SINK"):
            # pass through IMU control intents to internal bus
            pub.send_json(intent)            
        elif intent.get("type") == "RTP_SET_PARAMS":
            # pass through; HostRTP will clamp and apply
            pub.send_json({
                "type": "RTP_SET_PARAMS",
                "value": intent.get("value", {}),
            })
