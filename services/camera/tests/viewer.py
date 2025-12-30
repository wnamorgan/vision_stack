
import time
import cv2
import sys
import os
import zmq


from pathlib import Path
import sys

CAMERA_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CAMERA_ROOT))

from code.shared_memory_manager import SharedMemoryManager
from code.usb_camera import USB_Camera

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
 
    except KeyboardInterrupt:
        print("Stopping capture.")
        camera.stop_capture()  # Stop the camera capture on exit




if __name__ == "__main__":
    main()    
