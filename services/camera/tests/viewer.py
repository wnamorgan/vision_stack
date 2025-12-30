import time
import cv2
import zmq
import numpy as np
from multiprocessing import shared_memory

from pathlib import Path
import sys

CAMERA_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CAMERA_ROOT))

from code.shared_memory_manager import SharedMemoryManager
from code.usb_camera import USB_Camera


# ---- constants (must match camera allocation for now) ----
MAX_WIDTH  = 7680
MAX_HEIGHT = 4320

def main():
    # Create a USB camera instance (camera still owns SHM)
    from code.usb_camera import USB_Camera
    camera = USB_Camera()
    camera.start_capture()

    # ZeroMQ subscriber
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect("tcp://localhost:5555")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")

    width = height = channels = None
    shm = None
    frame_buf = None

    last_fps_calc = time.time()
    frame_count = 0
    fps = 0.0

    try:
        while True:
            msg = socket.recv_json()

            # First frame: attach to shared memory
            if shm is None:
                width    = msg["width"]
                height   = msg["height"]
                channels = msg["channels"]
                shm_name = msg["shm_name"]

                shm = shared_memory.SharedMemory(name=shm_name)
                frame_buf = np.ndarray(
                    (MAX_HEIGHT, MAX_WIDTH, channels),
                    dtype=np.uint8,
                    buffer=shm.buf[: MAX_WIDTH * MAX_HEIGHT * channels]
                )

                cv2.namedWindow("stream", cv2.WINDOW_NORMAL)
                cv2.resizeWindow("stream", width, height)

            frame_count += 1
            frame = frame_buf[:height, :width, :].copy()

            now = time.time()
            elapsed = now - last_fps_calc
            if elapsed >= 1.0:
                fps = frame_count / elapsed
                frame_count = 0
                last_fps_calc = now

            cv2.putText(
                frame, f"FPS: {fps:.1f}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                (255, 255, 255), 2, cv2.LINE_AA
            )

            cv2.imshow("stream", frame)
            if cv2.waitKey(1) == ord("q"):
                break

    except KeyboardInterrupt:
        pass
    finally:
        camera.stop_capture()
        if shm is not None:
            shm.close()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()


