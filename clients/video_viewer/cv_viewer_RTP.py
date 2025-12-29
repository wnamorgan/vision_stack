import time
import numpy as np
import cv2

import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst

# --------- CONFIG ----------
PORT = 5004
W, H = 1280, 720
# --------------------------


# Works in terminal
# gst-launch-1.0 -v   udpsrc port=5004 do-timestamp=true     caps="application/x-rtp,media=video,encoding-name=JPEG,payload=26,clock-rate=90000" !   rtpjpegdepay ! jpegdec ! autovideosink sync=false


Gst.init(None)


pipeline_str = (
    f"udpsrc port={PORT} caps=application/x-rtp,payload=26 ! "
    f"rtpjpegdepay ! jpegdec ! "
    f"video/x-raw,format=BGR ! "
    f"appsink name=sink sync=false drop=true max-buffers=1"
)


pipeline = Gst.parse_launch(pipeline_str)
appsink = pipeline.get_by_name("sink")

pipeline.set_state(Gst.State.PLAYING)

cv2.namedWindow("stream", cv2.WINDOW_NORMAL)
cv2.resizeWindow("stream", W, H)

last_fps_calc = time.time()
frame_count = 0
fps = 0.0

while True:
    # pull one frame (non-blocking-ish, bounded)
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

    # ---- FPS accounting (UNCHANGED LOGIC) ----
    frame_count += 1
    now = time.time()
    elapsed = now - last_fps_calc
    if elapsed >= 1.0:
        fps = frame_count / elapsed
        frame_count = 0
        last_fps_calc = now

    cv2.putText(
        frame, f"FPS: {fps:.1f}",
        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
        (255, 255, 255), 2, cv2.LINE_AA
    )

    cv2.imshow("stream", frame)
    if cv2.waitKey(1) == ord("q"):
        break

pipeline.set_state(Gst.State.NULL)
cv2.destroyAllWindows()

