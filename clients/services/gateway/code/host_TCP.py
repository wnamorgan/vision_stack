import time
import cv2
import numpy as np
import threading
import signal
import sys
import queue
import socket, struct

# ---- constants ----
DEV_VIDEO = "/dev/video0"
OUTPUT_URI = "webrtc://@:8554/output"
W, H, FPS = 1280, 720, 120
Q = 80  # jpeg quality
PORT = 5001



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

def setup_socket(port: int = PORT):
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(1)
    print(f"listening on :{port}")
    conn, addr = srv.accept()
    print("client", addr)
    return (conn,addr)


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


def process_frames(conn,frame_queue):
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
        conn.sendall(struct.pack("!I", len(data)) + data)


def signal_handler(sig, frame):
    global exit_flag
    print("\nGraceful exit initiated.")
    exit_flag = True



def main():
    # Set up graceful exit handling
    signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C

    # Create video capture object
    cap = open_cv_capture(DEV_VIDEO)

    (conn,addr) = setup_socket()

    
    # Create a thread-safe queue for frames
    frame_queue = queue.Queue(maxsize=1)  # Keep only the last frame in the queue

    # Start capture thread
    capture_thread = threading.Thread(target=capture_frames, args=(cap, frame_queue))
    capture_thread.start()

    
    # Start process thread
    process_thread = threading.Thread(target=process_frames, args=(conn, frame_queue))
    process_thread.start()

    # Wait for threads to finish (in this case, they run until exit_flag is set)
    capture_thread.join()
    process_thread.join()

    cap.release()
    conn.close() # Close Client Socket


if __name__ == "__main__":
    main()
