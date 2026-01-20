# Simple Web Canvas UI (GStreamer JPEG -> Browser)

This is a **minimal, standalone example** that:
- Serves a **single web page**
- Renders the **latest JPEG frame** into a browser `<canvas>`
- Is designed to plug into an existing **GStreamer RTP/JPEG receive pipeline**
- Keeps **UDP only on the backend** (browser uses HTTP locally)

No Dash. No WebRTC. No TCP across the data link.

---

## Directory layout

```
simple_web_canvas_ui/
├── server.py
└── static/
    └── index.html
```

---

## Requirements

- Python 3.8+
- pip packages:
  - fastapi
  - uvicorn

Install:
```bash
pip install fastapi uvicorn
```

---

## Configuration

Edit `services/gcs/.env`:

```env
RTP_PORT=5004
GCS_HTTP_PORT=8000
```

`RTP_PORT` controls the UDP input port for the JPEG RTP stream (matching whatever the dashboard publishes), and `GCS_HTTP_PORT` controls the HTTP port served to the browser.

## How to run

From this directory:

```bash
python server.py
```

Open a browser to:

```
http://localhost:8000
```

You should see a black page with a canvas that updates continuously.

---

## What this demo does

- `server.py`
  - Runs a tiny HTTP server
  - Serves `/frame.jpg` (latest JPEG only)
  - Serves `/` (the HTML UI)

- `index.html`
  - Draws `/frame.jpg` into a `<canvas>`
  - Captures click coordinates (logged to browser console)

---

## Replacing the fake image source

In `server.py`, remove this function:

```python
def fake_frame_producer():
    ...
```

and instead update `latest_jpeg` from your **GStreamer appsink callback**:

```python
def on_new_jpeg(jpeg_bytes):
    global latest_jpeg
    with frame_lock:
        latest_jpeg = jpeg_bytes
```

That is the **only required integration point**.

---

## Design intent (important)

- No buffering: latest frame wins
- Late frames are dropped
- UI reflects what the user sees *now*
- Clicks are pixel-accurate to the canvas

This is meant as a **sanity-check UI** before adding:
- metadata overlays
- UDP click forwarding
- WebSocket push

---

## Next steps (optional)

- Replace polling with WebSocket push
- Add `/click` POST endpoint
- Forward clicks via UDP to host system
- Overlay metadata text on the canvas

But do **not** add complexity until this works cleanly.

---

## License

Public domain / do whatever you want.
