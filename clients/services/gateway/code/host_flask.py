# mjpeg_flask.py
from flask import Flask, Response
import cv2, time

DEV = "/dev/video0"
W, H, FPS = 1280, 720, 120

app = Flask(__name__)
cap = cv2.VideoCapture(DEV, cv2.CAP_V4L2)
if not cap.isOpened(): raise RuntimeError(f"Can't open {DEV}")
cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
cap.set(cv2.CAP_PROP_FPS, FPS)

def gen():
    last = time.time(); n = 0; fps=0.0
    while True:
        ok, frame = cap.read()
        if not ok: continue

        n += 1
        if time.time() - last >= 2:
            fps = n/ (time.time()-last)
            print(f"MJPEG FPS≈{fps:.1f}")
            last = time.time(); n = 0
        cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                (255, 255, 255), 2, cv2.LINE_AA)  # White text with a thickness of 2
        ok, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok: continue

        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" +
               jpg.tobytes() + b"\r\n")

@app.get("/")
def index():
    return '<img src="/mjpeg" style="width:70%"/>'

@app.get("/mjpeg")
def mjpeg():
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)