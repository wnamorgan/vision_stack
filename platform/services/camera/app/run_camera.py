#!/usr/bin/env python3
"""Entrypoint for the camera service used by the Docker container."""

import os
import signal
import threading
import time
import logging
import sys
from glob import glob
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from code.usb_camera import USB_Camera

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _env_int(key: str, default: int) -> int:
    value = os.getenv(key)
    if value:
        return int(value)
    return default


def _shutdown_handler(event: threading.Event):
    def handler(signum, frame):
        logging.info("Shutdown signal (%s) received", signum)
        event.set()

    return handler


def _candidate_video_devices():
    preferred = os.getenv("CAM_DEVICE")
    if preferred and os.path.exists(preferred):
        return [preferred]
    devices = sorted(glob("/dev/video*"))
    if preferred and preferred not in devices:
        devices.insert(0, preferred)
    return devices


def get_aravis():
    return (False,None)

def get_usb():
    width = _env_int("CAM_WIDTH", 1280)
    height = _env_int("CAM_HEIGHT", 720)
    fps = _env_int("CAM_FPS", 120)
    last_error = None
    for device in _candidate_video_devices():
        try:
            logging.info(
                "Starting camera capture (width=%s height=%s fps=%s device=%s)",
                width,
                height,
                fps,
                device,
            )
            camera = USB_Camera(width=width, height=height, fps=fps, dev_video=device)
            camera.start_capture()
            return (True, camera)
        except RuntimeError as exc:
            last_error = exc
            logging.warning("Failed to open %s: %s", device, exc)
        except Exception as exc:
            last_error = exc
            logging.exception("Unexpected error opening %s", device)
    if last_error:
        logging.info("No USB camera available yet")
    return (False, None)

def get_camera():
    success, camera = get_aravis()
    if success:
        return (success, camera)
    
    success, camera = get_usb()
    if success:
        return (success, camera)

    return (False, None)

def main():
    stop_event = threading.Event()
    signal.signal(signal.SIGINT, _shutdown_handler(stop_event))
    signal.signal(signal.SIGTERM, _shutdown_handler(stop_event))

    (success, camera) = get_camera()

    try:
        while not stop_event.is_set():
            time.sleep(0.5)
            if not success:
                (success, camera) = get_camera()
    finally:
        if success:
            logging.info("Stopping camera capture")
            camera.stop_capture()


if __name__ == "__main__":
    main()
