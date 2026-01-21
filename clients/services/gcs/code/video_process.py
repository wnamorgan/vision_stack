import threading
import os
import time
import zmq
from multiprocessing import shared_memory
from fastapi import FastAPI
from fastapi.responses import Response
import uvicorn
from fastapi.responses import FileResponse
from pathlib import Path


VIDEO_HTTP_PORT = int(os.getenv("VIDEO_HTTP_PORT", "8000"))

ZMQ_FRAME_SUB = os.getenv("ZMQ_FRAME_SUB", "tcp://127.0.0.1:5572")
MAX_JPEG_BYTES = int(os.getenv("MAX_JPEG_BYTES", "8000000"))

latest_jpeg = None
lock = threading.Lock()


def shm_loop():
    """
    Wait for gateway notifications, then read encoded JPEG bytes from SHM.
    """
    global latest_jpeg

    ctx = zmq.Context.instance()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.LINGER, 0)
    sub.setsockopt(zmq.RCVHWM, 10)
    sub.connect(ZMQ_FRAME_SUB)
    sub.setsockopt_string(zmq.SUBSCRIBE, "")

    shm = None
    shm_buf = None

    while True:
        msg = sub.recv_json()
        if msg.get("type") != "GCS_FRAME_SHM":
            continue
        val = msg.get("value") or {}
        nbytes = int(val.get("nbytes", 0))
        if nbytes <= 0 or nbytes > MAX_JPEG_BYTES:
            continue

        # attach lazily / retry until SHM exists
        if shm is None:
            try:
                shm_name = val.get('shm_name')
                shm = shared_memory.SharedMemory(name=shm_name, create=False)
                shm_buf = shm.buf
            except FileNotFoundError:
                time.sleep(0.01)
                continue

        frame = bytes(shm_buf[:nbytes])
        with lock:
            latest_jpeg = frame


def run():

    threading.Thread(target=shm_loop, daemon=True).start()

    app = FastAPI()

    # Static assets live beside /app/code (default /app/static)
    STATIC_DIR = Path(os.getenv("STATIC_DIR", "/app/static"))

    @app.get("/video_panel")
    def video_panel():
        # Prevent stale panel HTML/CSS/JS; always fetch fresh from server
        return FileResponse(
            str(STATIC_DIR / "video_panel.html"),
            headers={
                "Cache-Control": "no-store, must-revalidate",
                "Pragma": "no-cache",
            },
        )
    
    @app.get("/frame.jpg")
    def frame():
        with lock:
            if latest_jpeg is None:
                return Response(status_code=204)
            # Explicitly disable caching in case a proxy ignores the query param trick
            return Response(
                latest_jpeg,
                media_type="image/jpeg",
                headers={
                    "Cache-Control": "no-store, must-revalidate",
                    "Pragma": "no-cache",
                },
            )

    uvicorn.run(app, host="0.0.0.0", port=VIDEO_HTTP_PORT, access_log=False)
