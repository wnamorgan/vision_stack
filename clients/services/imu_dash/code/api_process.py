import os
import socket
import threading
import logging
from typing import Optional, Dict, Any

import zmq
from fastapi import FastAPI
from fastapi.responses import Response
import uvicorn

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("imu_api")

HTTP_BIND_IMU_API_HOST = os.getenv("HTTP_BIND_IMU_API_HOST", "0.0.0.0")
HTTP_BIND_IMU_API_PORT = int(os.getenv("HTTP_BIND_IMU_API_PORT", "8200"))

ZMQ_CONNECT_PUSH_INTENT_HOST = os.getenv("ZMQ_CONNECT_PUSH_INTENT_HOST", "gateway")
ZMQ_CONNECT_PUSH_INTENT_PORT = int(os.getenv("ZMQ_CONNECT_PUSH_INTENT_PORT", "6000"))
ZMQ_PUSH_ENDPOINT = f"tcp://{ZMQ_CONNECT_PUSH_INTENT_HOST}:{ZMQ_CONNECT_PUSH_INTENT_PORT}"

ZMQ_CONNECT_SUB_TELEM_HOST = os.getenv("ZMQ_CONNECT_SUB_TELEM_HOST", "gateway")
ZMQ_CONNECT_SUB_TELEM_PORT = int(os.getenv("ZMQ_CONNECT_SUB_TELEM_PORT", "5570"))
ZMQ_TELEM_SUB = f"tcp://{ZMQ_CONNECT_SUB_TELEM_HOST}:{ZMQ_CONNECT_SUB_TELEM_PORT}"

UDP_INTENT_DST_IP = os.getenv("UDP_INTENT_DST_IP")
UDP_INTENT_DST_PORT = int(os.getenv("UDP_INTENT_DST_PORT", "9000"))

_latest_imu: Optional[Dict[str, Any]] = None
_imu_lock = threading.Lock()


def get_local_ip() -> str:
    env_ip = os.getenv("LOCAL_IP")
    if env_ip:
        return env_ip

    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if UDP_INTENT_DST_IP:
            s.connect((UDP_INTENT_DST_IP, UDP_INTENT_DST_PORT))
        else:
            s.connect(("192.0.2.1", 1))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    return "127.0.0.1"


def run() -> None:
    ctx = zmq.Context()
    push = ctx.socket(zmq.PUSH)
    push.connect(ZMQ_PUSH_ENDPOINT)
    log.info("[IMU_API] ZMQ PUSH connected to %s", ZMQ_PUSH_ENDPOINT)

    app = FastAPI()

    def _imu_sub_loop():
        zctx = zmq.Context()
        sub = zctx.socket(zmq.SUB)
        sub.connect(ZMQ_TELEM_SUB)
        sub.setsockopt_string(zmq.SUBSCRIBE, "")
        log.info("[IMU_API] ZMQ SUB connected to %s", ZMQ_TELEM_SUB)
        while True:
            msg = sub.recv_json()
            if msg.get("topic") is None:
                continue
            global _latest_imu
            with _imu_lock:
                _latest_imu = msg

    threading.Thread(target=_imu_sub_loop, daemon=True).start()

    @app.get("/imu")
    def imu():
        with _imu_lock:
            if _latest_imu is None:
                return Response(status_code=204)
            return _latest_imu

    @app.post("/imu/start")
    def imu_start():
        ip = get_local_ip()
        push.send_json({"type": "IMU_ADD_SINK", "ip": ip})
        return {"ok": True, "ip": ip}

    @app.post("/imu/stop")
    def imu_stop():
        ip = get_local_ip()
        push.send_json({"type": "IMU_REMOVE_SINK", "ip": ip})
        return {"ok": True, "ip": ip}

    uvicorn.run(app, host=HTTP_BIND_IMU_API_HOST, port=HTTP_BIND_IMU_API_PORT, log_level="info")


if __name__ == "__main__":
    run()
