# Camera Test Viewer

This folder includes a lightweight viewer that consumes the shared-memory feed published by the camera service. To confirm the camera is producing frames:

1. Start the camera service with the run script (which now mounts your workspace, shares IPC/network with the host, and publishes the SHM metadata).
   ```bash
   ./services/camera/run.sh
   ```
2. From the host (not inside the container), execute the test viewer.
   ```bash
   python services/camera/tests/test_container.py
   ```

The viewer attaches to `tcp://localhost:5555`, maps the shared memory segment, and opens an OpenCV window with an FPS overlay. Press `q` to exit.

## Local-Only Test

When you want to run against a local USB camera instead of the container, just execute:

```bash
python services/camera/tests/test_locally.py
```
