import cv2
from camera import Camera
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
    
    

import sys
import os
import zmq
# Add the root directory of your project to the sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from common.shm.shared_memory_manager import SharedMemoryManager
def cleanup_shared_memory(shm_name="frame_shm"):
    """Clean up any leftover shared memory before starting a new run."""
    try:
        # Check if shared memory exists and unlink it
        shm = SharedMemoryManager(shm_name=shm_name)
        if shm:
            shm.cleanup()  # Ensure it's cleaned up
            print(f"Cleaned up previous shared memory: {shm_name}")
    except Exception as e:
        print(f"No previous shared memory found or cleanup failed: {e}")


import time
def main():

    # Clean up leftover shared memory before starting
    cleanup_shared_memory()

    # Create a USB camera instance
    camera = USB_Camera()
    # Start camera capture
    camera.start_capture()

    # Set up ZeroMQ subscriber to listen for frame messages
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect("tcp://localhost:5555")  # Assuming publisher is on localhost

    # Subscribe to all messages (can be more specific if needed)
    socket.setsockopt_string(zmq.SUBSCRIBE, "")

    # FPS calculation
    frame_count = 0
    start_time = time.time()

    (width,height) = (1280,720)

    cv2.namedWindow("stream", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("stream", width, height)

    last_fps_calc = time.time()
    frame_count = 0
    fps = 0
    shm_manager = SharedMemoryManager()

    try:
        while True:
            message = socket.recv_string()  # Wait for a message from ZeroMQ
            frame_count += 1  # Increment the frame count
            frame = shm_manager.read_frame(width, height)
            now = time.time()
            elapsed = now - last_fps_calc
            if elapsed >= 1.0:
                fps = frame_count / elapsed
                frame_count = 0
                last_fps_calc = now
        
            fps_text = f"FPS: {fps:.1f}"
            cv2.putText(frame, fps_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                            (255, 255, 255), 2, cv2.LINE_AA)  
            if frame is not None:
                cv2.imshow("stream", frame)
            if cv2.waitKey(1) == ord("q"):
                break
        

            # Calculate FPS every second
            # elapsed_time = time.time() - start_time
            # if elapsed_time >= 1.0:
            #     fps = frame_count / elapsed_time
            #     print(f"SHM FPS: {fps:.1f}")  # Display FPS
            #     frame_count = 0  # Reset counter
            #     start_time = time.time()  # Reset start time
    except KeyboardInterrupt:
        print("Stopping capture.")
        camera.stop_capture()  # Stop the camera capture on exit




if __name__ == "__main__":
    main()    