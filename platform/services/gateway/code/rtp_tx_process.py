import os
import time
import numpy as np
import threading
import zmq
from .host_RTP import HostRTP
ZMQ_INTERNAL_SUB = os.getenv("ZMQ_INTERNAL_SUB", "tcp://localhost:5561")

def rtp_tx_process():
    host = HostRTP()

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(ZMQ_INTERNAL_SUB)
    sub.setsockopt_string(zmq.SUBSCRIBE, "")

    def control_loop():
        while True:
            msg = sub.recv_json()
            if msg.get("type") == "RTP_ADD_SINK":
                host._add_rtp_sink(msg["ip"], msg["port"])             
            elif msg.get("type") == "RTP_SET_PARAMS":
                host.apply_rtp_params(msg.get("value", {}))
    threading.Thread(target=control_loop, daemon=True).start()


    host.run()

def run():
    
    threading.Thread(target=rtp_tx_process, daemon=True).start()
    while True:
        time.sleep(1)
