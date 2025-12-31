import time
import cv2
import numpy as np
import threading
import signal
import sys
import queue
import socket, struct
import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst


# ---- constants ----
DEV_VIDEO = "/dev/video0"
OUTPUT_URI = "webrtc://@:8554/output"
W, H, FPS = 1280, 720, 120
Q = 80  # jpeg quality
PORT = 5004
DST_IP = "127.0.0.1"   # receiver
DST_IP = "192.168.1.255"

# Graceful exit flag
exit_flag = False


def open_cv_capture(dev: str):
    cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open {dev}")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    cap.set(cv2.CAP_PROP_FOURCC, fourcc)

    return cap

# Gstreamer works from linux as source
# gst-launch-1.0 -v   v4l2src device=/dev/video0 !   image/jpeg,framerate=120/1 !   rtpjpegpay pt=26 !   udpsink host=127.0.0.1 port=5004 sync=false async=false

def setup_pipeline(port: int = PORT, dst_ip: str = DST_IP, fps: int = FPS):
    Gst.init(None)
    pipeline_str = (
        f"appsrc name=src is-live=true block=false format=time do-timestamp=true "
        f"caps=image/jpeg,width={W},height={H},framerate={fps}/1 ! "
        f"rtpjpegpay pt=26 ! "
        f"udpsink host={dst_ip} port={port} sync=false async=false"
    )

    pipeline = Gst.parse_launch(pipeline_str)
    appsrc = pipeline.get_by_name("src")
    pipeline.set_state(Gst.State.PLAYING)
    return (appsrc,pipeline)


def capture_frames(cap, frame_queue):
    global exit_flag    
    while not exit_flag:
        ok, frame_bgr = cap.read()

        if ok and frame_bgr is not None:
            try:
                frame_queue.put_nowait(frame_bgr)
            except queue.Full:
                try:
                    frame_queue.get_nowait()  # drop the stale frame
                except queue.Empty:
                    pass
                frame_queue.put_nowait(frame_bgr)


def process_frames(appsrc,frame_queue):
    global exit_flag

    count = 0
    last = time.time()

    while not exit_flag:
        try: 
            # Block until a frame is available or timeout occurs
            frame_bgr = frame_queue.get(timeout=0.1)
        except queue.Empty: 
            # Timeout Occurred; check exit_flag or perform other tasks
            continue
        # Convert BGR -> RGBA
        if False:
            frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGBA)
        else:
            frame = frame_bgr

        # FPS
        count += 1
        now = time.time()
        if now - last >= 1.0:
            fps = count / (now - last)
            print(f"[TX] FPS={fps:.1f}")
            count = 0
            last = now    

        # Send Frames
        ok, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), Q])
        if not ok: continue
        data = jpg.tobytes()
    
        buf = Gst.Buffer.new_allocate(None, len(data), None)
        buf.fill(0, data)
        
        # optional-but-safe: stamp timing from your loop count (prevents weird pacing)
        buf.pts = Gst.util_uint64_scale(count, Gst.SECOND, FPS)
        buf.duration = Gst.util_uint64_scale(1, Gst.SECOND, FPS)
        
        flow = appsrc.emit("push-buffer", buf)
        if flow != Gst.FlowReturn.OK:
            print(f"[TX] push-buffer flow={flow}")
            break



def signal_handler(sig, frame):
    global exit_flag
    print("\nGraceful exit initiated.")
    exit_flag = True



def main():
    # Set up graceful exit handling
    signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C

    # Create video capture object
    cap = open_cv_capture(DEV_VIDEO)

    (appsrc,pipeline) = setup_pipeline()
    udpsink = pipeline.get_by_name("udpsink0")
    print("UDP HOST:", udpsink.get_property("host"))
    print("UDP PORT:", udpsink.get_property("port"))

    # Create a thread-safe queue for frames
    frame_queue = queue.Queue(maxsize=1)  # Keep only the last frame in the queue

    # Start capture thread
    capture_thread = threading.Thread(target=capture_frames, args=(cap, frame_queue))
    capture_thread.start()

    
    # Start process thread
    process_thread = threading.Thread(target=process_frames, args=(appsrc, frame_queue))
    process_thread.start()


    # Wait for threads to finish (in this case, they run until exit_flag is set)
    capture_thread.join()
    process_thread.join()

    cap.release()
    appsrc.emit("end-of-stream")
    pipeline.set_state(Gst.State.NULL)


if __name__ == "__main__":
    main()
