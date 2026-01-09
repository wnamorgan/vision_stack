import threading
import os
import numpy as np
import cv2
from fastapi import FastAPI
from fastapi.responses import Response
import uvicorn
from fastapi.responses import FileResponse
from pathlib import Path
import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst

RTP_PORT = int(os.getenv("RTP_PORT", "5004"))
VIDEO_HTTP_PORT = int(os.getenv("VIDEO_HTTP_PORT", "8000"))

latest_jpeg = None
lock = threading.Lock()


def gst_loop():
    global latest_jpeg
    Gst.init(None)

    # Direct JPEG passthrough with jitter buffer
    pipeline = Gst.parse_launch(
        f"udpsrc port={RTP_PORT} buffer-size=2097152 "
        f"caps=application/x-rtp,media=video,encoding-name=JPEG,payload=26 ! "
        f"rtpjitterbuffer latency=100 ! "  # Handle network jitter
        f"rtpjpegdepay ! appsink name=sink"
    )
    
    sink = pipeline.get_by_name("sink")
    
    # CRITICAL: These prevent blocking/freezing
    sink.set_property("emit-signals", True)
    sink.set_property("max-buffers", 1)    # Only keep 1 frame
    sink.set_property("drop", True)        # Drop old frames instead of blocking
    sink.set_property("sync", False)       # Don't wait for clock sync
    
    pipeline.set_state(Gst.State.PLAYING)

    while True:
        sample = sink.emit("try-pull-sample", 100_000_000)  # 100ms timeout
        if not sample:
            continue

        buf = sample.get_buffer()
        ok, mapinfo = buf.map(Gst.MapFlags.READ)
        if not ok:
            continue

        # Direct JPEG bytes - no decode/encode
        with lock:
            latest_jpeg = bytes(mapinfo.data)
        
        buf.unmap(mapinfo)



def run():
    threading.Thread(target=gst_loop, daemon=True).start()

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
