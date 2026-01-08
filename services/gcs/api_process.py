import os
import zmq
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
import logging
from typing import Optional

from control_schema import ControlIntent

CONTROL_API_PORT = int(os.getenv("CONTROL_API_PORT", "8100"))
ZMQ_PUSH = os.getenv("ZMQ_CONTROL")




class HelloReq(BaseModel):
    value: Optional[int] = 1


# import socket
# def get_local_ip():
#     s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#     try:
#         s.connect(("8.8.8.8", 80))  # no packets sent
#         ip = s.getsockname()[0]
#     finally:
#         s.close()
#     return ip


import psutil
import socket


def get_local_ip(subnet_prefix="192.168.1."):
    for iface, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET:
                ip = addr.address
                if ip.startswith(subnet_prefix):
                    return ip

    raise RuntimeError(f"No IPv4 address found on subnet {subnet_prefix}x")


def run():
    ctx = zmq.Context()
    sock = ctx.socket(zmq.PUSH)
    sock.bind(ZMQ_PUSH)    


    # TODO Move this send_json to make it connect to a dash button
    # one-time RTP subscribe on API startup
    import time
    time.sleep(10)
    gcs_ip = get_local_ip()
    # log = logging.getLogger("api")
    # logging.basicConfig(level=logging.INFO)
    # log.info(f"[api processing] ip address= {gcs_ip}")
    rtp_port = int(os.getenv("RTP_PORT", "5004"))
    sock.send_json({
        "type": "RTP_SUBSCRIBE",
        "value": {
            "ip": gcs_ip,
            "port": rtp_port
        }
    })

    app = FastAPI()

    @app.post("/control/hello")
    def hello(req: HelloReq):
        print("[API] sending intent to ZMQ")

        log = logging.getLogger("api")
        logging.basicConfig(level=logging.INFO)
        log.info("[API] handler entered")        
        intent = ControlIntent(type="HELLO", value=req.value)
        sock.send_json(intent.normalize())
        return {"status": "sent"}

    uvicorn.run(app, host="0.0.0.0", port=CONTROL_API_PORT)
