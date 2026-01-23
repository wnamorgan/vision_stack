#!/usr/bin/env python3
"""Entrypoint for the camera service used by the Docker container."""

import os
import signal
import threading
import time
import logging
import sys
import cv2
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


def _probe_usb_device(device: str) -> bool:
    # avoid OpenCV warnings on missing nodes
    if not os.path.exists(device) or not os.access(device, os.R_OK):
        return False
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap.release()
        return False
    cap.release()
    return True


def get_usb():
    width = _env_int("CAM_WIDTH", 1280)
    height = _env_int("CAM_HEIGHT", 720)
    fps = _env_int("CAM_FPS", 120)

    preferred = os.getenv("CAM_DEVICE")  # only if user pinned it
    last_error = None

    for device in _candidate_video_devices():
        if not _probe_usb_device(device):
            if preferred:  # only log specific device if user asked for it
                logging.info("No camera at %s yet", device)
            continue
        try:
            logging.info(
                "Starting camera capture (width=%s height=%s fps=%s device=%s)",
                width, height, fps, device,
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

    logging.info("No USB camera found yet")
    return (False, None)



import subprocess
def _aravis_n_devices_fresh_process() -> int:
    code = r"""
import gi
gi.require_version('Aravis', '0.8')
from gi.repository import Aravis
Aravis.update_device_list()
print(Aravis.get_n_devices())
"""

    try:
        out = subprocess.check_output([sys.executable, "-c", code], text=True).strip()
        return int(out) if out else 0
    except Exception as exc:
        logging.info("Aravis probe failed: %s", exc)
        return 0

def get_aravis():
    if os.getenv("USE_ARAVIS", "0") != "1":
        return (False, None)

    try:
        from code.aravis_camera import AravisCamera
    except Exception as exc:
        logging.info("Aravis not available: %s", exc)
        return (False, None)

    if _aravis_n_devices_fresh_process() == 0:
        logging.info("No Aravis devices found; skipping Aravis init.")
        return (False, None)

    try:
        camera = AravisCamera({})
        camera.start_capture()
        return (True, camera)
    except Exception as exc:
        logging.warning("Failed to start Aravis camera: %s", exc)
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
            if success and camera.failed_event.is_set():
                logging.warning("Camera capture failed; restarting discovery")
                camera.stop_capture(unlink=False)
                success = False
                camera = None
            if not success:
                (success, camera) = get_camera()
    finally:
        if success:
            logging.info("Stopping camera capture")
            camera.stop_capture(unlink=True)


if __name__ == "__main__":
    main()
