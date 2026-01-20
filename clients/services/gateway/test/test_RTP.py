import threading
import signal
from pathlib import Path
import sys
import time
import signal

UI_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(UI_ROOT))

from code.host_RTP import *
from usb_cam_to_shm import USB_Camera

def main():

    rtp = HostRTP()
    signal.signal(signal.SIGINT, rtp.signal_handler)

    rtp_thread = threading.Thread(target=rtp.run, daemon=True)
    rtp_thread.start()

    # This host streamer will work fine with either resolution camera and always
    # produces a 1280x720 resolution image on RTP
    if False:
        camera = USB_Camera(1920,1280,60,"/dev/video0")
    else:
        camera = USB_Camera() # 120 Hz
    camera.start_capture()

    try:
        while not rtp.stop_event.is_set():
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        camera.stop_capture()
        rtp.stop_event.set()
        rtp_thread.join()          

if __name__ == "__main__":
    main()