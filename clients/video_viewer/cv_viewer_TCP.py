import socket, struct
import numpy as np
import cv2
import time
IP   = "192.168.1.50"  # <-- set Jetson IP
IP   = "127.0.0.0"
PORT = 5001

def recvn(s, n):
    b = bytearray()
    while len(b) < n:
        p = s.recv(n - len(b))
        if not p: return None
        b += p
    return bytes(b)

s = socket.socket()
s.connect((IP, PORT))
cv2.namedWindow("stream", cv2.WINDOW_NORMAL)
cv2.resizeWindow("stream", 1280, 720)
last_fps_calc = 0.0
frame_count=0
while True:
    hdr = recvn(s, 4)
    if hdr is None: break
    (n,) = struct.unpack("!I", hdr)
    data = recvn(s, n)
    if data is None: break
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    
    now = time.time()
    frame_count += 1
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
