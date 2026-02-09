import os
import zmq
import threading
import time
from multiprocessing import shared_memory
import numpy as np
import logging
class Camera:
    frame_id_counter=0
    def __init__(self):

        self.setup_shm()

        # ZeroMQ publisher
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        host = os.getenv("ZMQ_BIND_PUB_CAMERA_HOST", "0.0.0.0")
        port = int(os.getenv("ZMQ_BIND_PUB_CAMERA_PORT", "5555"))
        pub_endpoint = f"tcp://{host}:{port}"
        self.socket.bind(pub_endpoint)  # ZeroMQ PUB socket

        self.exit_flag = threading.Event()  # For signaling thread to stop
        self.failed_event = threading.Event()  # Set when capture loop fails
        self.capture_thread = threading.Thread(target=self.capture_frames)  # Create the capture thread
        self.log = logging.getLogger("camera")
        logging.basicConfig(level=logging.INFO)
        self.frame_id = 0
        
    def setup_shm(self):
        def env_int(var, default):
            value = os.getenv(var)
            return int(value) if value else default

        self.shm_name = os.getenv("SHM_NAME", "frame_shm")
        self.max_width = env_int("MAX_WIDTH", 7680)
        self.max_height = env_int("MAX_HEIGHT", 4320)
        self.channels = env_int("CHANNELS", 3)
    
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
            # Reuse existing SHM so consumers keep a valid handle on restart.
            self.shm = shared_memory.SharedMemory(name=self.shm_name)
        self._ensure_shm_permissions()
    
        buf = self.shm.buf
    
        # ---- pixel buffer (STABLE OFFSET) ----
        self.image_buf = np.ndarray(
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


    def write_image_to_shared_memory(self, image):
        """Write the captured image into shared memory. Use seq to detect tearing"""
        h, w, c = image.shape
    
        self.seq[0] += 1              # write start (odd)
        self.meta[:] = (w, h, self.channels)
        self.image_buf[:h, :w, :c] = image
        self.seq[0] += 1              # write complete (even)

    def capture_frames(self):
        """Main loop to capture frames continuously, write to shared memory, and send ZeroMQ notifications."""
        fail_threshold = int(os.getenv("CAM_FAILURE_THRESHOLD", "5"))
        fail_count = 0
        info_period = float(os.getenv("INFO_PERIOD", "10.0"))
        last_log_t = time.time()
        while not self.exit_flag.is_set():  # Check the exit flag to stop the thread
            try:
                ok, frame = self.capture_frame()  # Capture a frame (implementation in child class)
            except Exception:
                self.log.exception("Capture failed with exception; stopping")
                self.failed_event.set()
                break
            if not ok or frame is None:
                fail_count += 1
                if fail_count >= fail_threshold:
                    self.log.warning("Capture failed %s times; stopping", fail_count)
                    self.failed_event.set()
                    break
                continue
            fail_count = 0
            image = frame['image']
            metadata = frame['metadata']
            metadata['frame_id'] = self.frame_id
            metadata['t_cam_sw_ns'] = time.time_ns()
            self.frame_id += 1
            now = time.time()
            if now - last_log_t >= info_period:
                self.log.info("[Camera] Frame Count = %s", self.frame_id)
                last_log_t = now
            self.write_image_to_shared_memory(image)
            self.send_frame_metadata(metadata)

    def start_capture(self):
        """Start the capture thread."""
        self.exit_flag.clear()
        self.capture_thread.start()

    def stop_capture(self, unlink: bool = True):
        """Stop the capture thread gracefully."""
        self.exit_flag.set()  # Signal the thread to stop
        self.capture_thread.join()  # Wait for the thread to finish
        
        try:
            self.shm.close()
            if unlink:
                self.shm.unlink()
        except Exception:
            pass

        self.socket.close()
        self.context.term()

    def send_frame_metadata(self, metadata):      
    
        self.frame_id_counter += 1
    
        msg = {
            "type": "frame",
            "source": "camera",            
            "shm_name": self.shm_name,
            "metadata": metadata,
            "frame_id": self.frame_id_counter,
        }

        self.socket.send_json(msg)            

    def _ensure_shm_permissions(self):
        if os.name != "posix":
            return

        if self.shm_name.startswith("/"):
            path = f"/dev/shm{self.shm_name}"
        else:
            path = f"/dev/shm/{self.shm_name}"

        try:
            os.chmod(path, 0o666)
        except FileNotFoundError:
            pass
