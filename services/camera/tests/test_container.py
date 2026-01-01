"""Standalone camera viewer + diagnostics for the containerized camera service."""

import os
import time
import cv2
import zmq
import numpy as np
import mmap
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _env_int(key: str, default: int) -> int:
    value = os.getenv(key)
    return int(value) if value is not None else default


def _shm_path(name: str) -> str:
    return name if name.startswith("/") else f"/dev/shm/{name}"


def main():
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect("tcp://localhost:5555")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")

    shm_map = None
    frame_view = None
    width = height = channels = None

    max_width = _env_int("MAX_WIDTH", 7680)
    max_height = _env_int("MAX_HEIGHT", 4320)
    max_channels = _env_int("CHANNELS", 3)

    window_name = "camera container"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1280, 720)
    last_fps_calc = time.time()
    frame_count = 0
    fps = 0.0

    try:
        while True:
            msg = socket.recv_json()

            if shm_map is None:
                width = int(msg["width"])
                height = int(msg["height"])
                channels = int(msg["channels"])
                shm_name = msg["shm_name"]
                buffer_size = max_width * max_height * max_channels
                fd = os.open(_shm_path(shm_name), os.O_RDONLY)
                shm_map = mmap.mmap(fd, buffer_size, access=mmap.ACCESS_READ)
                os.close(fd)
                frame_raw = np.ndarray(
                    (max_height, max_width, max_channels),
                    dtype=np.uint8,
                    buffer=shm_map,
                )
                frame_view = frame_raw[:height, :width, :channels]
                logging.info(
                    "attached SHM %s (%dx%dx%d) view from %dx%dx%d",
                    shm_name,
                    width,
                    height,
                    channels,
                    max_width,
                    max_height,
                    max_channels,
                )

            frame_count += 1
            frame = frame_view.copy()

            now = time.time()
            elapsed = now - last_fps_calc
            if elapsed >= 1.0:
                fps = frame_count / elapsed
                last_fps_calc = now
                frame_count = 0
                print(f"[viewer] FPS={fps:.1f}")

            cv2.putText(
                frame,
                f"FPS: {fps:.1f}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            cv2.imshow(window_name, frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    except KeyboardInterrupt:
        logging.info("interrupted")
    finally:
        if shm_map is not None:
            shm_map.close()
        socket.close()
        context.term()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
