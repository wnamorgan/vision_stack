import zmq
import threading
from multiprocessing import shared_memory
import numpy as np
import cv2

class Camera:
    frame_id_counter=0
    def __init__(self):

        self.setup_shm()

        # ZeroMQ publisher
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.bind("tcp://*:5555")  # ZeroMQ PUB socket

        self.exit_flag = threading.Event()  # For signaling thread to stop
        self.capture_thread = threading.Thread(target=self.capture_frames)  # Create the capture thread

    def setup_shm(self):
        self.shm_name = "frame_shm"
        self.max_width = 7680
        self.max_height = 4320
        self.channels = 3
    
        # ---- sizes ----
        self.pixel_bytes = self.max_width * self.max_height * self.channels
        self.meta_bytes  = 32  # seq + dims + future-proof padding
        self.shm_size    = self.pixel_bytes + self.meta_bytes
    
        try:
            self.shm = shared_memory.SharedMemory(
                create=True,
                name=self.shm_name,
                size=self.shm_size,
            )
        except FileExistsError:
            old = shared_memory.SharedMemory(name=self.shm_name)
            old.unlink()
            old.close()
            self.shm = shared_memory.SharedMemory(
                create=True,
                name=self.shm_name,
                size=self.shm_size,
            )
    
        buf = self.shm.buf
    
        # ---- pixel buffer (STABLE OFFSET) ----
        self.frame_buf = np.ndarray(
            (self.max_height, self.max_width, self.channels),
            dtype=np.uint8,
            buffer=buf[:self.pixel_bytes],
        )
    
        # ---- metadata (AFTER pixels) ----
        meta_offset = self.pixel_bytes
    
        self.seq = np.ndarray(
            (1,),
            dtype=np.uint64,
            buffer=buf,
            offset=meta_offset,
        )
    
        self.meta = np.ndarray(
            (3,),  # width, height, channels
            dtype=np.uint32,
            buffer=buf,
            offset=meta_offset + 8,
        )
    
        # initialize
        self.seq[0] = 0

    def capture_frame(self):
        """To be implemented by child classes. Capture frame from camera."""
        raise NotImplementedError("capture_frame() must be implemented in child class")


    def write_frame_to_shared_memory(self, frame):
        """Write the captured frame into shared memory. Use seq to detect tearing"""
        h, w, c = frame.shape
    
        self.seq[0] += 1              # write start (odd)
        self.meta[:] = (w, h, self.channels)
        self.frame_buf[:h, :w, :c] = frame
        self.seq[0] += 1              # write complete (even)

    def capture_frames(self):
        """Main loop to capture frames continuously, write to shared memory, and send ZeroMQ notifications."""
        while not self.exit_flag.is_set():  # Check the exit flag to stop the thread
            ok, frame_bgr = self.capture_frame()  # Capture a frame (implementation in child class)
            if ok and frame_bgr is not None:
                self.write_frame_to_shared_memory(frame_bgr)
                self.send_frame_metadata(frame_bgr)

    def start_capture(self):
        """Start the capture thread."""
        self.exit_flag.clear()
        self.capture_thread.start()

    def stop_capture(self):
        """Stop the capture thread gracefully."""
        self.exit_flag.set()  # Signal the thread to stop
        self.capture_thread.join()  # Wait for the thread to finish
        
        try:
            self.shm.close()
            self.shm.unlink()
        except Exception:
            pass

        self.socket.close()
        self.context.term()

    def send_frame_metadata(self, frame):
        h, w, c = frame.shape
    
        self.frame_id_counter += 1
    
        msg = {
            "shm_name": self.shm_name,
            "width": w,
            "height": h,
            "channels": c,
            "frame_id": self.frame_id_counter,
        }
    
        self.socket.send_json(msg)            


class USB_Camera(Camera):
    def __init__(self, width=1280, height=720, fps=120, dev_video="/dev/video0"):
        super().__init__()
        self.width=width
        self.height=height
        self.fps=120
        self.dev_video = dev_video
        self.cap = self.open_cv_capture()

    def open_cv_capture(self):
        """Open the USB camera using OpenCV."""
        cap = cv2.VideoCapture(self.dev_video, cv2.CAP_V4L2)
        if not cap.isOpened():
            raise RuntimeError(f"Could not open {self.dev_video}")

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)  

        # Attempt to Apply User Settings
        self.width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        self.height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        self.fps = cap.get(cv2.CAP_PROP_FPS)
        
        # Print Actual Camera Settings Used
        print(f"Width set to: {self.width}")
        print(f"Height set to: {self.height}")
        print(f"FPS set to: {self.fps}")

        return cap


    def capture_frame(self):
        """Capture a frame from the USB camera."""
        ok, frame_bgr = self.cap.read()
        if ok and frame_bgr is not None:
            return ok, frame_bgr  # Ensure this is a tuple with exactly two elements
        return False, None  # If something goes wrong, return False and None
            