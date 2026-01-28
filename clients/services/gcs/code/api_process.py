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

from .control_schema import ControlIntent

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")

HTTP_BIND_CONTROL_HOST = os.getenv("HTTP_BIND_CONTROL_HOST", "0.0.0.0")
HTTP_BIND_CONTROL_PORT = int(os.getenv("HTTP_BIND_CONTROL_PORT", "8100"))
ZMQ_CONNECT_PUSH_INTENT_HOST = os.getenv("ZMQ_CONNECT_PUSH_INTENT_HOST", "gateway")
ZMQ_CONNECT_PUSH_INTENT_PORT = int(os.getenv("ZMQ_CONNECT_PUSH_INTENT_PORT", "6000"))
ZMQ_PUSH_ENDPOINT = f"tcp://{ZMQ_CONNECT_PUSH_INTENT_HOST}:{ZMQ_CONNECT_PUSH_INTENT_PORT}"
ZMQ_CONNECT_SUB_TELEM_HOST = os.getenv("ZMQ_CONNECT_SUB_TELEM_HOST", "127.0.0.1")
ZMQ_CONNECT_SUB_TELEM_PORT = int(os.getenv("ZMQ_CONNECT_SUB_TELEM_PORT", "5570"))
ZMQ_META_SUB = f"tcp://{ZMQ_CONNECT_SUB_TELEM_HOST}:{ZMQ_CONNECT_SUB_TELEM_PORT}"
UDP_INTENT_DST_IP = os.getenv("UDP_INTENT_DST_IP")
UDP_INTENT_DST_PORT = int(os.getenv("UDP_INTENT_DST_PORT", "9000"))

_latest_meta: Optional[Dict[str, Any]] = None
_meta_lock = threading.Lock()

_latest_link_usage: Optional[Dict[str, Any]] = None
_link_lock = threading.Lock()

def get_local_ip() -> str:
    """
    Best-effort local IP selection for the machine/container running this API.
    Prefer explicit env override; otherwise pick a non-loopback address.
    """
    env_ip = os.getenv("LOCAL_IP")
    if env_ip:
        return env_ip

    # Try hostname resolution first
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    # UDP "connect" trick (no packets sent) to select the source IP the OS would
    # use to reach the platform gateway. This avoids hardcoding LOCAL_IP per site.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Prefer routing to the configured gateway destination if present.
        if UDP_INTENT_DST_IP:
            s.connect((UDP_INTENT_DST_IP, UDP_INTENT_DST_PORT))
        else:
            # Fallback: documentation IP; doesn't require reachable internet.
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

class VideoSettingsReq(BaseModel):
    scale: float
    w: int
    h: int
    fps: int
    quality: int

class PixelClickReq(BaseModel):
    image_id: str = "video_main"
    frame_id: int = -1  # placeholder until Task 4
    x_px: int
    y_px: int
    x_n: float  # 0..1
    y_n: float  # 0..1


def run() -> None:
    if not ZMQ_PUSH_ENDPOINT:
        raise RuntimeError("ZMQ_CONNECT_PUSH_INTENT_HOST/PORT env var is required")

    ctx = zmq.Context()
    sock = ctx.socket(zmq.PUSH)
    sock.connect(ZMQ_PUSH_ENDPOINT)
    log.info(f"[API] ZMQ PUSH connected to {ZMQ_PUSH_ENDPOINT}")

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

            mtype = msg.get("type")
            val = msg.get("value")
            if not isinstance(val, dict):
                continue

            if mtype == "FRAME_META":
                global _latest_meta
                with _meta_lock:
                    _latest_meta = val
                continue

            if mtype == "LINK_USAGE":
                global _latest_link_usage
                with _link_lock:
                    _latest_link_usage = val
                # 1 Hz message: OK to log
                log.info("[LINK] %s", val)
                continue


    threading.Thread(target=_meta_sub_loop, daemon=True).start()

    @app.get("/frame_meta")
    def frame_meta():
        with _meta_lock:
            if _latest_meta is None:
                return Response(status_code=204)
            return _latest_meta

    @app.get("/link_usage")
    def link_usage():
        with _link_lock:
            if _latest_link_usage is None:
                #return Response(status_code=204)
                return {}
            return _latest_link_usage

    @app.post("/control/stream_subscribe")
    def stream_subscribe(req: HelloReq):
        gcs_ip = get_local_ip()
        rtp_port = int(os.getenv("RTP_RX_LISTEN_PORT", "5004"))
        intent = ControlIntent(type="RTP_SUBSCRIBE", value={"ip": gcs_ip, "port": rtp_port})
        sock.send_json(intent.normalize())
        return {"status": "sent", "ip": gcs_ip, "port": rtp_port}

    @app.post("/control/pixel_click")
    def pixel_click(req: PixelClickReq):
        payload: Dict[str, Any] = req.model_dump()
        intent = ControlIntent(type="PIXEL_CLICK", value=payload)
        sock.send_json(intent.normalize())
        return {"status": "sent", **payload}


    @app.post("/control/video_settings")
    def video_settings(req: VideoSettingsReq):
        # clamp/sanitize (keep it simple)
        q = max(10, min(95, int(req.quality)))
        fps = max(1, min(120, int(req.fps)))
        w = max(64, int(req.w))
        h = max(64, int(req.h))
        scale = float(req.scale)

        intent = ControlIntent(
            type="RTP_SET_PARAMS",
            value={"scale": scale, "w": w, "h": h, "fps": fps, "quality": q},
        )
        sock.send_json(intent.normalize())
        return {"status": "sent", "value": intent.normalize()["value"]}

    uvicorn.run(app, host=HTTP_BIND_CONTROL_HOST, port=HTTP_BIND_CONTROL_PORT, access_log=False)


if __name__ == "__main__":
    run()
