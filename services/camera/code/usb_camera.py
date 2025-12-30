import cv2
from .camera_base import Camera
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
    
    
