import sys
import os

import zmq
import numpy as np
from .shared_memory_manager import SharedMemoryManager
import time
import threading

class Camera:
    frame_id_counter=0
    def __init__(self):
        # SharedMemoryManager is now a member of this class
        
        # This information should be read in, not hard coded here
        shm_name="frame_shm"
        max_width=7680
        max_height=4320
        channels=3
        
        self.shm_manager = SharedMemoryManager(shm_name=shm_name, max_width=max_width, max_height=max_height, channels=channels)
        
        # ZeroMQ publisher
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.bind("tcp://*:5555")  # ZeroMQ PUB socket

        self.exit_flag = threading.Event()  # For signaling thread to stop
        self.capture_thread = threading.Thread(target=self.capture_frames)  # Create the capture thread


    def capture_frame(self):
        """To be implemented by child classes. Capture frame from camera."""
        raise NotImplementedError("capture_frame() must be implemented in child class")

    def write_frame_to_shared_memory(self, frame):
        """Write the captured frame into shared memory."""
        self.shm_manager.write_frame(frame)

    def send_zeromq_message(self):
        """Send ZeroMQ message indicating new frame is ready."""
        self.socket.send(b"new_frame")

    def capture_frames(self):
        """Main loop to capture frames continuously, write to shared memory, and send ZeroMQ notifications."""
        while not self.exit_flag.is_set():  # Check the exit flag to stop the thread
            ok, frame_bgr = self.capture_frame()  # Capture a frame (implementation in child class)

            if ok and frame_bgr is not None:
                try:
                    # Write frame to shared memory
                    self.write_frame_to_shared_memory(frame_bgr)
                    # Send ZeroMQ message
                    self.send_zeromq_message()
                except Exception as e:
                    print(f"Error writing frame to shared memory: {e}")

    def start_capture(self):
        """Start the capture thread."""
        self.exit_flag.clear()
        self.capture_thread.start()

    def stop_capture(self):
        """Stop the capture thread gracefully."""
        self.exit_flag.set()  # Signal the thread to stop
        self.capture_thread.join()  # Wait for the thread to finish

    def send_frame_metadata(self, frame):
        """Send frame metadata (ID and size) via ZeroMQ as a JSON message."""
        # Extract size from frame shape (rows, columns, channels)
        frame_size = frame.shape[:3]  # (r, c, h)

        # Increment frame ID counter
        self.frame_id_counter += 1
        frame_id = self.frame_id_counter

        # Create the message
        message = {
            "frame_id": frame_id,
            "size": list(frame_size)  # Convert tuple to list for JSON serialization
        }    