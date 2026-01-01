# Dashboard Service — local testing

This service runs `HostRTP`, which subscribes to the camera’s shared-memory metadata (`ZMQ_SUB_ENDPOINT`) and streams it out via RTP.

## Building

```bash
./services/dashboard/build.sh
```

## Running

The dashboard runs headless and simply publishes RTP frames to `RTP_DST_IP:RTP_PORT`. Use your preferred RTP viewer or `clients/video_viewer/cv_viewer_RTP.py` to verify the stream.

### Running with Docker (`run.sh`)

`run.sh` uses the same image but overrides `ZMQ_SUB_ENDPOINT` to `localhost` (set `FORCE_LOCAL=1` if you need that explicitly) while keeping the Compose `.env` values untouched. It shares IPC/network so the dashboard can open the camera’s shared memory when you run the camera service locally. Run the script and then attach to the camera stream (e.g., via the GStreamer viewer) to confirm the pipeline:

```bash
./services/dashboard/run.sh
```

### Running with Docker Compose

When Compose owns the topology, use service hostnames instead of `localhost` so the dashboard connects to the camera on the shared network. Drop the `--network=host` flags (compose handles networking) and place these values in the Compose-provided `.env` (or override per profile):

```bash
ZMQ_SUB_ENDPOINT=tcp://camera:5555
RTP_PORT=5004
RTP_DST_IP=127.0.0.1
```

Bring up the stack with:

```bash
docker compose up --build
```

Compose already shares IPC via `ipc: host`, which lets the dashboard access the camera’s shared memory segment, and the dashboard service overrides `ZMQ_SUB_ENDPOINT` so it always connects to `camera:5555`.

## Tests

Run the existing `test_RTP.py` from `services/dashboard/test` to exercise the same `HostRTP` + `USB_Camera` loop the dashboard uses.

### Running the dashboard test manually

```bash
cd services/dashboard/test
python test_RTP.py
```

Because the script already spawns its own `USB_Camera` publisher and `HostRTP` consumer, you can run it entirely inside the dashboard container. Ensure the camera `.env` or Compose service is providing shared memory/ZMQ metadata before launching the test.

## Viewing the RTP Stream

Point your local RTP viewer at the dashboard output (port `5004` by default). This command uses GStreamer to receive and display the JPEG stream:

```bash
gst-launch-1.0 -v \
  udpsrc port=5004 do-timestamp=true \
  caps="application/x-rtp,media=video,encoding-name=JPEG,payload=26,clock-rate=90000" ! \
  rtpjpegdepay ! jpegdec ! autovideosink sync=false
```

Leave it running to see the same frames the dashboard is publishing; close the window or hit `Ctrl+C` when you’re done.
