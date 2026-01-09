import os
import socket
import logging
from typing import Optional, Dict, Any
import threading
import zmq
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
import uvicorn

from control_schema import ControlIntent

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")

CONTROL_API_PORT = int(os.getenv("CONTROL_API_PORT"))
ZMQ_PUSH = os.getenv("ZMQ_CONTROL")  # e.g. "tcp://*:5559" (GCS side PUSH bind)
ZMQ_META_SUB = os.getenv("ZMQ_META_SUB", "tcp://127.0.0.1:5570")  # from gcs/udp_rx_process.py

_latest_meta: Optional[Dict[str, Any]] = None
_meta_lock = threading.Lock()

def get_local_ip() -> str:
    """
    Best-effort local IP selection for the machine/container running this API.
    Prefer explicit env override; otherwise pick a non-loopback address.
    """
    env_ip = os.getenv("GCS_IP") or os.getenv("LOCAL_IP")
    if env_ip:
        return env_ip

    # Try hostname resolution first
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    # UDP "connect" trick (no packets sent) to select outbound interface
    # Uses a documentation IP; doesn't require reachable internet.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 1))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    return "127.0.0.1"


class HelloReq(BaseModel):
    value: Optional[int] = 1

class JpegQualityReq(BaseModel):
    quality: int

class PixelClickReq(BaseModel):
    image_id: str = "video_main"
    frame_id: int = -1  # placeholder until Task 4
    x_px: int
    y_px: int
    x_n: float  # 0..1
    y_n: float  # 0..1


def run() -> None:
    if not ZMQ_PUSH:
        raise RuntimeError("ZMQ_CONTROL env var is required (e.g., tcp://*:5559)")

    ctx = zmq.Context()
    sock = ctx.socket(zmq.PUSH)
    sock.bind(ZMQ_PUSH)
    log.info(f"[API] ZMQ PUSH bound at {ZMQ_PUSH}")

    app = FastAPI()

    # Allow browser (video panel on :8000) to POST to this API (:8100).
    # For production you’ll tighten origins; for now keep it simple.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


    # ---- Meta cache: SUB from ZMQ (produced by udp_rx_process) ----
    def _meta_sub_loop():
        zctx = zmq.Context()
        sub = zctx.socket(zmq.SUB)
        sub.connect(ZMQ_META_SUB)
        sub.setsockopt_string(zmq.SUBSCRIBE, "")
        log.info(f"[API] ZMQ META SUB connected to {ZMQ_META_SUB}")
        while True:
            msg = sub.recv_json()
            if msg.get("type") != "FRAME_META":
                continue
            md = msg.get("value")
            if not isinstance(md, dict):
                continue
            global _latest_meta
            with _meta_lock:
                _latest_meta = md

    threading.Thread(target=_meta_sub_loop, daemon=True).start()

    @app.get("/frame_meta")
    def frame_meta():
        with _meta_lock:
            if _latest_meta is None:
                return Response(status_code=204)
            return _latest_meta

    @app.post("/control/stream_subscribe")
    def stream_subscribe(req: HelloReq):
        gcs_ip = get_local_ip()
        rtp_port = int(os.getenv("RTP_PORT", "5004"))
        intent = ControlIntent(type="RTP_SUBSCRIBE", value={"ip": gcs_ip, "port": rtp_port})
        sock.send_json(intent.normalize())
        return {"status": "sent", "ip": gcs_ip, "port": rtp_port}

    @app.post("/control/pixel_click")
    def pixel_click(req: PixelClickReq):
        payload: Dict[str, Any] = req.model_dump()
        intent = ControlIntent(type="PIXEL_CLICK", value=payload)
        sock.send_json(intent.normalize())
        return {"status": "sent", **payload}


    @app.post("/control/jpeg_quality")
    def jpeg_quality(req: JpegQualityReq):
        q = int(req.quality)
        intent = ControlIntent(type="RTP_SET_QUALITY", value={"quality": q})
        sock.send_json(intent.normalize())
        return {"status": "sent", "quality": q}

    uvicorn.run(app, host="0.0.0.0", port=CONTROL_API_PORT)


if __name__ == "__main__":
    run()
