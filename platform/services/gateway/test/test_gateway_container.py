"""Self-contained gateway container smoke test."""

import signal
import threading
import time
from pathlib import Path
import sys

UI_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(UI_ROOT))

from code.host_RTP import HostRTP
from usb_cam_to_shm import USB_Camera


def main():
    viewer = HostRTP()
    signal.signal(signal.SIGINT, viewer.signal_handler)
    signal.signal(signal.SIGTERM, viewer.signal_handler)

    viewer_thread = threading.Thread(target=viewer.run, daemon=True)
    viewer_thread.start()

    camera = USB_Camera()
    camera.start_capture()

    try:
        while not viewer.stop_event.is_set():
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        camera.stop_capture()
        viewer.stop_event.set()
        viewer_thread.join()


if __name__ == "__main__":
    main()
