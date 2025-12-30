import zmq
import threading
from multiprocessing import shared_memory
import numpy as np

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
        self.shm_size = self.max_width * self.max_height * self.channels
    
        try:
            self.shm = shared_memory.SharedMemory(
                create=True,
                name=self.shm_name,
                size=self.shm_size,
            )
        except FileExistsError:
            # Previous instance left it behind — attach, then unlink & recreate
            old = shared_memory.SharedMemory(name=self.shm_name)
            old.unlink()
            old.close()
            self.shm = shared_memory.SharedMemory(
                create=True,
                name=self.shm_name,
                size=self.shm_size,
            )
    
        self.frame_buf = np.ndarray(
            (self.max_height, self.max_width, self.channels),
            dtype=np.uint8,
            buffer=self.shm.buf,
        )
       

    def capture_frame(self):
        """To be implemented by child classes. Capture frame from camera."""
        raise NotImplementedError("capture_frame() must be implemented in child class")

    def write_frame_to_shared_memory(self, frame):
        """Write the captured frame into shared memory."""
        h, w, c = frame.shape
        self.frame_buf[:h, :w, :] = frame


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