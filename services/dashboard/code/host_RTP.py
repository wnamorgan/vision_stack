import os
import time
import cv2
import numpy as np
import threading
import queue
import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst
from multiprocessing import shared_memory
import zmq

# ---- defaults ----
W, H, FPS = 1280, 720, 120
Q = 80  # jpeg quality
ZMQ_SUB_ENDPOINT = os.getenv("ZMQ_SUB_ENDPOINT", "tcp://localhost:5555")
RTP_PORT = int(os.getenv("RTP_PORT", "5004"))
RTP_DST_IP = os.getenv("RTP_DST_IP", "127.0.0.1")

class HostRTP:
    def __init__(self):
        self.MAX_HEIGHT = 4320
        self.MAX_WIDTH  = 7680
        self.shm=None
        self.frame_queue = queue.Queue(maxsize=1)  # Keep only the last frame in the queue
        self.stop_event = threading.Event()
        Gst.init(None)
        self.setup_pipeline()

        self.context = zmq.Context()
        self.sub_socket = self.context.socket(zmq.SUB)
        self.sub_socket.connect(ZMQ_SUB_ENDPOINT)
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")
        self.sub_socket.RCVTIMEO = 200

    def run(self):

        zmq_thread = threading.Thread(target=self.zmq_sub_loop)
        process_thread = threading.Thread(target=self.process_frames)
    
        zmq_thread.start()    
        process_thread.start()
    
        try:
            while not self.stop_event.is_set():
                time.sleep(0.2)
        finally:
            # ---- coordinated shutdown ----
            zmq_thread.join()

            process_thread.join()
    
            self.appsrc.emit("end-of-stream")
            self.pipeline.set_state(Gst.State.NULL)

            if self.shm is not None:
                self.shm.close()
            
            self.sub_socket.close()
            self.context.term()

    def setup_pipeline(self, port: int = RTP_PORT, dst_ip: str = RTP_DST_IP, fps: int = FPS):
        self.port   = port
        self.dst_ip = dst_ip
        self.fps    = fps

        
        pipeline_str = (
            f"appsrc name=src is-live=true block=false format=time do-timestamp=true "
            f"caps=image/jpeg,width={W},height={H},framerate={fps}/1 ! "
            f"rtpjpegpay pt=26 ! "
            f"udpsink host={dst_ip} port={port} sync=false async=false"
        )
    
        self.pipeline = Gst.parse_launch(pipeline_str)
        self.appsrc   = self.pipeline.get_by_name("src")
        self.pipeline.set_state(Gst.State.PLAYING)

    def process_frames(self):

        count = 0
        last = time.time()
           
        while not self.stop_event.is_set():
            try: 
                # Block until a frame is available or timeout occurs
                frame_bgr = self.frame_queue.get(timeout=0.1)

            except queue.Empty: 
                # Timeout Occurred; check exit_flag or perform other tasks
                continue
            # Convert BGR -> RGBA
            if False:
                frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGBA)
            else:
                frame = frame_bgr


            # FPS
            count += 1
            now = time.time()
            if now - last >= 1.0:
                fps = count / (now - last)
                print(f"[TX] FPS={fps:.1f}")
                count = 0
                last = now    
    
            # Send Frames
            frame = cv2.resize(frame, (W, H), interpolation=cv2.INTER_LINEAR)
            ok, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), Q])
            if not ok: continue
            data = jpg.tobytes()
        
            buf = Gst.Buffer.new_allocate(None, len(data), None)
            buf.fill(0, data)
            
            # optional-but-safe: stamp timing from your loop count (prevents weird pacing)
            buf.pts = Gst.util_uint64_scale(count, Gst.SECOND, FPS)
            buf.duration = Gst.util_uint64_scale(1, Gst.SECOND, FPS)
            
            flow = self.appsrc.emit("push-buffer", buf)
            if flow != Gst.FlowReturn.OK:
                print(f"[TX] push-buffer flow={flow}")
                self.stop_event.set()
                break



    
    def signal_handler(self, sig, frame):
        print("\nGraceful exit initiated.")
        self.stop_event.set()

    def zmq_sub_loop(self):

        
        while not self.stop_event.is_set():
            try:
                msg = self.sub_socket.recv_json()
            except zmq.Again:
                continue

            self.width    = msg["width"]
            self.height   = msg["height"]
            self.channels = msg["channels"]
            self.shm_name = msg["shm_name"]

            # First frame: attach to SHM
            if self.shm is None:
                self.shm = shared_memory.SharedMemory(name=self.shm_name)
                self.frame_buf = np.ndarray(
                    (self.MAX_HEIGHT, self.MAX_WIDTH, self.channels),  # Use instance vars here
                    dtype=np.uint8,
                    buffer=self.shm.buf[: self.MAX_WIDTH * self.MAX_HEIGHT * self.channels]
                )

            # Read latest frame (copy semantics preserved)
            frame = self.frame_buf[:self.height, :self.width, :self.channels].copy()

            # TEMP: feed into existing RTP path
            try:
                self.frame_queue.put_nowait(frame)
            except queue.Full:
                try:
                    self.frame_queue.get_nowait()
                except queue.Empty:
                    pass
                self.frame_queue.put_nowait(frame)



# Gstreamer works from linux as source
# gst-launch-1.0 -v   v4l2src device=/dev/video0 !   image/jpeg,framerate=120/1 !   rtpjpegpay pt=26 !   udpsink host=127.0.0.1 port=5004 sync=false async=false
