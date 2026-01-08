import threading
import os
import numpy as np
import cv2
from fastapi import FastAPI
from fastapi.responses import Response
import uvicorn
from fastapi.responses import FileResponse

import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst

RTP_PORT = int(os.getenv("RTP_PORT", "5004"))
VIDEO_HTTP_PORT = int(os.getenv("VIDEO_HTTP_PORT", "8000"))

latest_jpeg = None
lock = threading.Lock()

# def gst_loop():
#     global latest_jpeg
#     Gst.init(None)

#     pipeline = Gst.parse_launch(
#         f"udpsrc port={RTP_PORT} caps=application/x-rtp,media=video,encoding-name=JPEG,payload=26 ! "
#         f"rtpjpegdepay ! jpegdec ! videoconvert ! video/x-raw,format=BGR ! appsink name=sink"
#     )
#     sink = pipeline.get_by_name("sink")
#     pipeline.set_state(Gst.State.PLAYING)

#     while True:
#         sample = sink.emit("try-pull-sample", 1_000_000_000)
#         if not sample:
#             continue

#         buf = sample.get_buffer()
#         caps = sample.get_caps().get_structure(0)
#         w, h = caps.get_value("width"), caps.get_value("height")

#         ok, mapinfo = buf.map(Gst.MapFlags.READ)
#         if not ok:
#             continue

#         frame = np.frombuffer(mapinfo.data, np.uint8).reshape(h, w, 3).copy()
#         buf.unmap(mapinfo)

#         ok, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
#         if ok:
#             with lock:
#                 latest_jpeg = jpg.tobytes()


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

    @app.get("/")
    def index():
        return FileResponse("static/index.html")
    
    @app.get("/frame.jpg")
    def frame():
        with lock:
            if latest_jpeg is None:
                return Response(status_code=204)
            return Response(latest_jpeg, media_type="image/jpeg")

    uvicorn.run(app, host="0.0.0.0", port=VIDEO_HTTP_PORT, access_log=False)
