# Reusable ZeroMQ Container Pattern (Thread-Based, Low-Latency) — Rev C

This document defines a **reusable, evolvable ZeroMQ container pattern** for low-latency, multi-process systems.
Rev C incorporates final correctness fixes, portability improvements, and documentation polish.

---

## Changelog

- **Rev A**: Initial production-hardening (thread lifecycle, error handling, linger)
- **Rev B**: Topic validation, signal handling example, explicit tradeoffs
- **Rev C**: Fixed signal-handler shutdown, cross-platform wait, changelog, quick start, documentation polish

---

## 1. General Design Principles (Invariant)

These principles are **non-negotiable**:

1. **Containers are reusable units**
   - No container hard-codes peers or topology.
   - All wiring is external (Compose, Kubernetes, test harnesses).

2. **Configuration via environment only**
   - `.env` files define endpoints, topics, and behavior.
   - Code contains zero addresses or ports.

3. **Sockets are unidirectional**
   - One socket = one direction (PUB *or* SUB).
   - A process may own multiple sockets.

4. **Latency over abstraction**
   - Favor blocking I/O and deterministic behavior.
   - Avoid async frameworks unless required.

5. **Topology is external**
   - Reuse is achieved by rewiring, not rewriting.

---

## 2. Explicit Design Choices

### 2.1 Thread-Based Blocking SUB (Required)

- One **dedicated thread per inbound socket**
- Blocking `recv()` with bounded timeout
- Explicit shutdown signal + join

### 2.2 Latency Classes (Defined)

A **latency class** is a group of messages with similar delivery urgency:

- Control: <10 ms
- Telemetry: <100 ms
- Logging/metrics: <1 s

Different latency classes **must not share sockets**.

### 2.3 PUB Binds, SUB Connects (Default)

- PUB sockets `bind()`
- SUB sockets `connect()`

This is a default, not universal.
Fan-in scenarios may require reversing this.

### 2.4 Inherent ZeroMQ Behaviors (Must Be Designed Around)

- **Slow joiner**: early PUB messages may be dropped
  - Mitigation: allow 50-100 ms after `bind()` or synchronize explicitly
- **Automatic reconnect**
- **Best-effort delivery**

---

## 3. Example (Camera Container)

### 3.1 Topic Conventions (Required)

- Format: `<component>.<message_type>`
- Allowed: ASCII alphanumeric + dots
- Max length: 64 characters
- UTF-8 encoded, no null bytes

---

### 3.2 Camera `.env`

```env
ZMQ_SUB_ENDPOINT=tcp://dashboard:6000
ZMQ_SUB_TOPICS=camera.cmd

ZMQ_PUB_ENDPOINT=tcp://*:5555
ZMQ_PUB_TOPICS=camera.frame,camera.heartbeat
```

`ZMQ_PUB_TOPICS` is informational and intended for validation, documentation, or external tooling.

---

### 3.3 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app
RUN pip install pyzmq

COPY camera.py .
CMD ["python", "camera.py"]
```

---

### 3.4 Docker Compose (Illustrative)

```yaml
services:
  camera:
    build: ./camera
    env_file: ./camera/.env
    networks: [vision]

  dashboard:
    build: ./dashboard
    env_file: ./dashboard/.env
    networks: [vision]

networks:
  vision:
    driver: bridge
```

---

### 3.5 Camera ZeroMQ Class (Rev C)

```python
import os
import zmq
import threading
import logging
import signal
import re

log = logging.getLogger(__name__)

TOPIC_RE = re.compile(r"^[A-Za-z0-9.]{1,64}$")

def require(var):
    v = os.getenv(var)
    if not v:
        raise RuntimeError(f"Missing env var: {var}")
    return v

def validate_topic(t: str):
    if not TOPIC_RE.match(t):
        raise ValueError(f"Invalid topic: {t}")
    return t

class CameraZMQ:
    """
    Requires logging.basicConfig() to be configured before instantiation.
    """
    def __init__(self):
        self.sub_endpoint = require("ZMQ_SUB_ENDPOINT")
        self.sub_topics = [validate_topic(t) for t in require("ZMQ_SUB_TOPICS").split(",")]

        self.pub_endpoint = require("ZMQ_PUB_ENDPOINT")

        self.ctx = zmq.Context()

        self.sub = self.ctx.socket(zmq.SUB)
        self.sub.connect(self.sub_endpoint)
        for t in self.sub_topics:
            self.sub.setsockopt_string(zmq.SUBSCRIBE, t)
        self.sub.setsockopt(zmq.RCVTIMEO, 500)

        self.pub = self.ctx.socket(zmq.PUB)
        self.pub.setsockopt(zmq.LINGER, 0)
        self.pub.bind(self.pub_endpoint)

        self.shutdown = threading.Event()

        self.rx_thread = threading.Thread(
            target=self._rx_loop,
            daemon=False
        )
        self.rx_thread.start()

    def _rx_loop(self):
        try:
            while not self.shutdown.is_set():
                try:
                    topic, payload = self.sub.recv_multipart()
                    self.handle_control(topic, payload)
                except zmq.Again:
                    continue
        except zmq.ZMQError as e:
            if not self.shutdown.is_set():
                log.exception("ZMQ error in RX loop: %s", e)
        except Exception:
            log.exception("Unhandled exception in RX loop")

    def handle_control(self, topic: bytes, payload: bytes):
        try:
            topic_str = topic.decode("utf-8")
        except UnicodeDecodeError:
            log.error("Received non-UTF8 topic")
            return
        log.info("CTRL %s %s", topic_str, payload)

    def publish(self, topic: str, payload: bytes):
        validate_topic(topic)
        self.pub.send_multipart([topic.encode("utf-8"), payload])

    def close(self):
        self.shutdown.set()
        self.rx_thread.join(timeout=2.0)
        if self.rx_thread.is_alive():
            log.warning("RX thread did not stop cleanly")
        self.sub.close()
        self.pub.close()
        self.ctx.term()

def main():
    logging.basicConfig(level=logging.INFO)
    cam = CameraZMQ()

    shutdown_event = threading.Event()

    def _shutdown(*_):
        shutdown_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    shutdown_event.wait()
    cam.close()
```

---

## 4. Reuse, Extension, and Testing

### 4.1 Reuse

- Containers are reusable by changing only `.env`
- Topology changes require no code changes

### 4.2 Extension

- Add sockets for new latency classes
- Add REQ/REP for reliable control
- Use shared memory for data plane

### 4.3 Testing (Required)

- Test containers in isolation using `inproc://`
- Validate startup order, shutdown behavior, and topic mismatches

### 4.4 Observability (Optional)

- Message rate counters
- Error counters
- External monitoring (e.g., Prometheus)

---

## 5. Quick Start

1. Build containers:
   ```bash
   docker-compose build
   ```
2. Run:
   ```bash
   docker-compose up
   ```
3. Expect logs indicating control subscription and frame publication.

---

## 6. Troubleshooting

- **No messages**
  - Verify topics match exactly
  - Verify bind/connect roles
  - Allow time for slow joiner

- **Shutdown hangs**
  - Check LINGER settings
  - Watch for RX thread warnings

---

This pattern is conservative by design.
Deviations should be documented in deployment notes.
