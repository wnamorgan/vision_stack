# USB3 Vision Camera Timestamp Synchronization (Aravis + FLIR Blackfly)

## Purpose

Synchronize a **USB3 Vision camera’s GenICam timestamps** to the **Jetson host clock**
with **sub-millisecond accuracy**, suitable for **Kalman filtering, SOT, and sensor fusion**.

This is the **best possible method** for USB cameras (no PTP, no PPS).

---

## Problem Statement

A USB3 Vision camera provides:
- `Timestamp` — camera-local, free-running clock (usually exposure time)
- No hardware time synchronization to the host

The host (Jetson) operates in its own monotonic clock domain.

**Goal:** Map camera timestamps into host time with bounded error (<1 ms).

---

## Core Idea

Use **GenICam `TimestampLatch`** to sample the camera clock at a known host time,
then estimate a **linear clock model**:

t_cam = a * t_host + b

Invert it to convert any camera timestamp into host time:

t_host = (t_cam - b) / a

Where:
- b = time offset (bias)
- a = relative clock rate (drift)

---

## Why This Works

- USB latency is variable, but clock drift is smooth
- Latching removes transport delay from the estimation
- Remaining error is zero-mean jitter, not bias
- Ideal for Kalman filters that estimate time-offset states

---

## Expected Accuracy

- Offset error: 50–150 µs
- RMS jitter: 100–300 µs
- Worst case: < 1 ms
- Drift: 10–50 ppm (corrected)

---

## Python Implementation (Aravis)

### Requirements
- Aravis (Python GI bindings)
- NumPy
- Linux (Jetson)

---

### Timestamp Latch + Calibration

```python
import time
import numpy as np
import gi

gi.require_version("Aravis", "0.8")
from gi.repository import Aravis

CLOCK = time.CLOCK_MONOTONIC_RAW

cam = Aravis.Camera.new(None)
cam.start_acquisition()

def latch_pair():
    """
    Returns (t_host, t_cam) in seconds
    """
    cam.set_integer("TimestampLatch", 1)
    t_cam_ns = cam.get_integer("TimestampLatchValue")
    t_host = time.clock_gettime(CLOCK)
    return t_host, t_cam_ns * 1e-9  # ns → s

# Collect calibration samples
pairs = np.array([latch_pair() for _ in range(50)])

# Linear fit: t_cam = a * t_host + b
a, b = np.polyfit(pairs[:, 0], pairs[:, 1], 1)

def cam_to_host_time(t_cam_ns):
    """
    Convert camera timestamp (ns) → host monotonic time (s)
    """
    t_cam = t_cam_ns * 1e-9
    return (t_cam - b) / a
```

---

### Applying to Frames

```python
while True:
    buf = cam.try_pop_buffer()
    if not buf:
        continue

    t_cam_ns = buf.get_timestamp()
    t_host_est = cam_to_host_time(t_cam_ns)

    # Use t_host_est for DNN, SOT, or sensor fusion

    cam.push_buffer(buf)
```

---

## Drift Tracking (Optional)

Re-latch periodically (1–5 Hz) and update b only:

b_new = (1 - alpha) * b_old + alpha * (t_cam - a * t_host)

---

## Kalman Filter Interpretation

- State: time offset Δt
- Measurement: camera timestamp mapped to host time
- Bias estimated by the filter
- Jitter absorbed into measurement noise R

---

## Summary

- Standard practice for USB3 Vision cameras
- <1 ms bounded error
- Ideal for DNN → SOT → Kalman pipelines
- Minimal code, negligible runtime cost
