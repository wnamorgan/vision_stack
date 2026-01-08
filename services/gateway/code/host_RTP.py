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
from multiprocessing import resource_tracker
import zmq
import logging

# ---- defaults ----
W = int(os.getenv("RTP_WIDTH", 1280))
H = int(os.getenv("RTP_HEIGHT", 720))
Q = 80  # jpeg quality
ZMQ_SUB_ENDPOINT = os.getenv("ZMQ_SUB_ENDPOINT", "tcp://localhost:5555")
ZMQ_FRAME_META_PUB = os.getenv("ZMQ_FRAME_META_PUB", "tcp://*:5562") 
RTP_PORT = int(os.getenv("RTP_PORT", "5004"))
RTP_DST_IP = os.getenv("RTP_DST_IP", "127.0.0.1")

class HostRTP:
    def __init__(self):
        self.MAX_HEIGHT = 4320
        self.MAX_WIDTH  = 7680
        self.shm=None
        self.frame_queue = queue.Queue(maxsize=1)  # Keep only the last frame in the queue
        self.tx_queue    = queue.Queue(maxsize=1)  # tx-rate → sender
        self.stop_event = threading.Event()
        Gst.init(None)
        self.setup_pipeline()

        self.context = zmq.Context()
        self.sub_socket = self.context.socket(zmq.SUB)
        self.sub_socket.connect(ZMQ_SUB_ENDPOINT)
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")
        self.sub_socket.RCVTIMEO = 200 

        # Side-channel publisher (frame metadata)
        self.meta_pub = self.context.socket(zmq.PUB)
        self.meta_pub.setsockopt(zmq.SNDHWM, 1)   # keep only latest if congested
        self.meta_pub.setsockopt(zmq.LINGER, 0)
        self.meta_pub.bind(ZMQ_FRAME_META_PUB)

        self.log = logging.getLogger("RTP Rx")
        logging.basicConfig(level=logging.INFO)
        self.frame_id = 0 
        self.Tx_Hz = float(os.getenv("RTP_TX_HZ", "30"))
        self.rtp_sinks = {}
        self._add_rtp_sink(RTP_DST_IP, RTP_PORT)


    def run(self):

        zmq_thread = threading.Thread(target=self.zmq_sub_loop)
        process_thread = threading.Thread(target=self.process_frames)
        tx_thread = threading.Thread(target=self.tx_rate_loop)


        zmq_thread.start()    
        process_thread.start()
        tx_thread.start()
        try:
            while not self.stop_event.is_set():
                time.sleep(0.2)
        finally:
            # ---- coordinated shutdown ----
            zmq_thread.join()

            process_thread.join()

            tx_thread.join()

        for (pipeline, appsrc) in self.rtp_sinks.values():
            appsrc.emit("end-of-stream")
            pipeline.set_state(Gst.State.NULL)

            if self.shm is not None:
                self.shm.close()
            
            self.sub_socket.close()
            self.meta_pub.close()
            self.context.term()

    def setup_pipeline(self, port: int = RTP_PORT, dst_ip: str = RTP_DST_IP):
        self.port   = port
        self.dst_ip = dst_ip

        pipeline_str = (
            f"appsrc name=src is-live=true block=false format=time do-timestamp=true "
            f"caps=image/jpeg,width={W},height={H} ! "
            f"rtpjpegpay pt=26 ! "
            f"udpsink host={dst_ip} port={port} sync=false async=false"
        )


        self.pipeline = Gst.parse_launch(pipeline_str)
        self.appsrc   = self.pipeline.get_by_name("src")
        self.pipeline.set_state(Gst.State.PLAYING)

    def process_frames(self):

        count = 0
        last = time.time()
        fps = None   
        while not self.stop_event.is_set():
            try: 
                # Block until a frame is available or timeout occurs
                frame_bgr, msg, frame_id = self.tx_queue.get(timeout=0.1)

            except queue.Empty: 
                # Timeout Occurred; check exit_flag or perform other tasks
                continue
            # Convert BGR -> RGBA
            if False:
                frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGBA)
            else:
                frame = frame_bgr


            # Side-channel: publish frame_id (Task 4 will extend this to include full msg)
            try:
                self.meta_pub.send_json(
                    {"type":"FRAME_META", "value": msg["metadata"]},
                    flags=zmq.NOBLOCK
                )
            except zmq.Again:
                pass


            # Send Frames
            frame = cv2.resize(frame, (W, H), interpolation=cv2.INTER_LINEAR)

            # FPS
            count += 1
            now = time.time()
            if now - last >= 1.0:
                fps = count / (now - last)
                print(f"[TX] FPS={fps:.1f}")
                count = 0
                last = now   

            if True and fps:
                cv2.putText(
                    frame, f"FPS: {fps:.1f}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                    (255, 255, 255), 2, cv2.LINE_AA
                )
            ok, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), Q])
            if not ok: continue
            data = jpg.tobytes()
        
            buf = Gst.Buffer.new_allocate(None, len(data), None)
            buf.fill(0, data)
            
            dead_sinks = []
            for (ip, port), (pipeline, appsrc) in list(self.rtp_sinks.items()):
                flow = appsrc.emit("push-buffer", buf)
                if flow != Gst.FlowReturn.OK:
                    self.log.warning(
                        "RTP sink %s:%d push-buffer failed (%s), removing",
                        ip, port, flow
                    )
                    dead_sinks.append((ip, port))
            
            # remove failed sinks after iteration
            for key in dead_sinks:
                pipeline, appsrc = self.rtp_sinks.pop(key)
                appsrc.emit("end-of-stream")
                pipeline.set_state(Gst.State.NULL)
    
            # Optional (remove if you don't want any new behavior/logging)
            if not self.rtp_sinks:
                self.log.warning("No RTP sinks remain")



    
    def signal_handler(self, sig, frame):
        print("\nGraceful exit initiated.")
        self.stop_event.set()

    def enqueue_frame(self,msg):

        self.shm_name = msg["shm_name"]
        metadata      = msg["metadata"]
        self.width    = metadata["w"]
        self.height   = metadata["h"]
        self.channels = metadata["c"]


        # First frame: attach to SHM
        if self.shm is None:
            self.shm = shared_memory.SharedMemory(name=self.shm_name)
            resource_tracker.unregister(self.shm._name, "shared_memory")
            self.image_buf = np.ndarray(
                (self.MAX_HEIGHT, self.MAX_WIDTH, self.channels),  # Use instance vars here
                dtype=np.uint8,
                buffer=self.shm.buf[: self.MAX_WIDTH * self.MAX_HEIGHT * self.channels]
            )

        # Read latest frame (copy semantics preserved)
        image = self.image_buf[:self.height, :self.width, :self.channels].copy()
        self.frame_id +=1
        frame = (image,msg,self.frame_id)
        if self.frame_id % 1000 == 0:
            self.log.info(f"[RTP Rx] Frame Count = {self.frame_id}")  
        # TEMP: feed into existing RTP path
        try:
            self.frame_queue.put_nowait(frame)
        except queue.Full:
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                pass
            self.frame_queue.put_nowait(frame)

    def zmq_sub_loop(self):

        while not self.stop_event.is_set():
            try:
                msg = self.sub_socket.recv_json()
            except zmq.Again:
                continue

            if msg.get("type") == "frame":
                self.enqueue_frame(msg)



    def tx_rate_loop(self):
        
        next_tx = time.time()
   
        while not self.stop_event.is_set():
            period = 1.0 / self.Tx_Hz
            
            now = time.time()
            if now < next_tx:
                time.sleep(next_tx - now)
            next_tx += period
   
            frame = self.frame_queue.get()   # block for latest frame

            try:
                self.tx_queue.put_nowait(frame)
            except queue.Full:
                self.tx_queue.get_nowait()
                self.tx_queue.put_nowait(frame)

    def _add_rtp_sink(self, ip, port):
        if (ip, port) in self.rtp_sinks:
            self.log.info("RTP sink %s:%d already exists, ignoring", ip, port)
            return
        self.log.info("Adding RTP sink %s:%d", ip, port)
        pipeline_str = (
            f"appsrc name=src is-live=true block=false format=time do-timestamp=true "
            f"caps=image/jpeg,width={W},height={H} ! "
            f"rtpjpegpay pt=26 ! "
            f"udpsink host={ip} port={port} sync=false async=false"
        )
        pipeline = Gst.parse_launch(pipeline_str)
        appsrc = pipeline.get_by_name("src")
        pipeline.set_state(Gst.State.PLAYING)
        self.rtp_sinks[(ip, port)] = (pipeline, appsrc)


# Gstreamer works from linux as source
# gst-launch-1.0 -v   v4l2src device=/dev/video0 !   image/jpeg,framerate=120/1 !   rtpjpegpay pt=26 !   udpsink host=127.0.0.1 port=5004 sync=false async=false
