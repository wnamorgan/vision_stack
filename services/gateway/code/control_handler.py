# This file would handle the received UDP messages
# For example, mapping the message to actions like controlling platform components.

import os
import zmq
import logging

ZMQ_INTENT_SUB   = os.getenv("ZMQ_INTENT_SUB",   "tcp://localhost:5560")
ZMQ_INTERNAL_PUB = os.getenv("ZMQ_INTERNAL_PUB", "tcp://*:5561")

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
        elif intent.get("type") == "RTP_SET_QUALITY":
            cmd = {
                "type": "RTP_SET_QUALITY",
                "quality": int(intent["value"]["quality"]),
            }
            pub.send_json(cmd)