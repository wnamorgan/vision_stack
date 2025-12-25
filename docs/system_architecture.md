# Architecture & Design Notes — vision_stack

This document captures **design rationale and implementation direction** for the `vision_stack` repository.
It intentionally answers not just *what* the system does, but *how and why* design decisions were made.
This is a working engineering document and may be trimmed once the system stabilizes.

---

## Calibration

- Implement calibration as a dedicated service: `services/calibration/`.
- Two calibration workflows are supported:
  - **Point-source alignment**: aligns camera to IMU/gyro using a point source.
  - **Target-board calibration**: uses Zhang’s method to recover intrinsics/extrinsics.
- Calibration is expected to run in **lab** and possibly **captive** modes; it is typically disabled in **flight**.

**Invocation model**
- UI or client publishes `cal.request`.
- Calibration service publishes progress on `cal.status` and results on `cal.result`.

**Persistence**
- Calibration results are written to a versioned directory (e.g., `calibration/results/`) and also summarized in messages.

---

## Dashboard (Dash)

- A single Dash application is used across all environments.
- Dash runs **headless** by default; UI access is optional via exposed ports.
- Controls are **capability-gated**, not environment-forked.
  - Services publish `*.status` or a `system.capabilities` message.
  - The UI enables/disables controls accordingly (e.g., calibration disabled in flight).

**Design rule**
- Dash is never part of the control or timing-critical path.
- Dash is UI + command + status only.

---

## Latency Considerations

- Dash introduces negligible latency when kept out of the data path.
- Control loops (tracking, gimbal) operate on shared memory and ZMQ metadata only.
- Human-facing preview latency is acceptable and expected to be higher than control latency.

---

## Streaming Plan (Preview Video)

- Capture **full-frame** images from the camera over **USB3**.
- Perform **software ROI** selection downstream (tracking/overlay stage).
- Hardware ROI on the camera is treated as an optimization and not required initially.

**Preview modes**
- **ROI preview (default)**: overlayed ROI stream for low bandwidth and responsiveness.
- **Full-frame preview (debug)**: downscaled full-frame for context and reacquisition.

**Encoding**
- Use Jetson/Tegra hardware encoder (**NVENC**) for H.264/H.265.
- Configure encoder for low latency (avoid B-frames, long lookahead).

**Transport**
- Preview is delivered via **WebRTC** for low-latency in-browser viewing.
- Dash embeds the WebRTC stream; it does not serve frames itself.

**Architecture rule**
- Tracking and control timing must never depend on the preview stream.

---

## Telemetry & Transport

- Telemetry is treated as a transport problem, not an application concern.
- All communication assumes IP connectivity.
  - Ethernet when available.
  - Radios (e.g., Doodle) are transparent IP links.
- If needed, a `telemetry_bridge` service may exist, but core services remain agnostic.

---

## Profile Expectations

### Flight
- External flight software publishes:
  - `imu.data`
  - `nav.solution`
  - cue/command topics
- Local IMU and calibration services are disabled.
- Dashboard typically not exposed.

### Captive
- Local IMU service enabled.
- Calibration may be enabled.
- Dashboard enabled.
- Cue generation may come from a simulated flight interface.

### Lab
- Simulated publishers enabled.
- Calibration enabled.
- Dashboard enabled.
- Full observability and replay expected.

---

## Design Principles (Summary)

- One contract, multiple producers (sim vs real).
- Containers define responsibility boundaries.
- ZMQ defines system interfaces.
- Shared memory is used for bulk data.
- UI is observational, not authoritative.
