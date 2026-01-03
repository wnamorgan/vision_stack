import threading
import os

import numpy as np
import cv2

from fastapi import FastAPI
from fastapi.responses import Response, FileResponse
import uvicorn

import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst

# -----------------------------
# Configuration
# -----------------------------
RTP_PORT = int(os.getenv("RTP_PORT", "5004"))
GCS_HTTP_PORT = int(os.getenv("VID_HTTP_PORT", "8000"))
# -----------------------------
# Global frame storage
# -----------------------------
latest_jpeg = None
frame_lock = threading.Lock()

# -----------------------------
# GStreamer receive thread
# -----------------------------
def gst_receive_loop():
    global latest_jpeg

    Gst.init(None)

    pipeline_str = (
        f"udpsrc port={RTP_PORT} caps=application/x-rtp,media=video,encoding-name=JPEG,payload=26 ! "
        f"rtpjpegdepay ! jpegdec ! "
        f"videoconvert ! video/x-raw, format=BGR, width=1280, height=720 ! "
        f"appsink name=sink"
    )
    
    pipeline = Gst.parse_launch(pipeline_str)
    appsink = pipeline.get_by_name("sink")
    
    pipeline.set_state(Gst.State.PLAYING)

    while True:

        sample = appsink.emit("try-pull-sample", 1_000_000_000)
        if sample is None:
            continue

        buf = sample.get_buffer()
        caps = sample.get_caps().get_structure(0)
        w = caps.get_value("width")
        h = caps.get_value("height")
    
        ok, mapinfo = buf.map(Gst.MapFlags.READ)
        if not ok:
            continue

        frame = np.frombuffer(mapinfo.data, np.uint8).reshape((h, w, 3)).copy()
        buf.unmap(mapinfo)


        ok, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok:
            continue

        with frame_lock:
            latest_jpeg = jpg.tobytes()

# -----------------------------
# FastAPI server
# -----------------------------
app = FastAPI()

@app.get("/")
def index():
    return FileResponse("static/index.html")

@app.get("/frame.jpg")
def frame():
    with frame_lock:
        if latest_jpeg is None:
            return Response(status_code=204)
        return Response(latest_jpeg, media_type="image/jpeg")

# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":

    threading.Thread(target=gst_receive_loop, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=GCS_HTTP_PORT)
