# Project Backlog

This document captures what must be built, why, and what “done” means. This document is subordinate to the [system](./system_architecture.md) and [project](./project_architecture.md) architecture documents.

---

## Context (Current State)

- Real-time object detection demonstrated on Jetson Orin Nano (toy-car demo).
- Vision sources (FLIR, visible camera, 4QD) are platform options, not fused.
- Core architecture: cue → acquire → track, with IMU + gimbal + modular pub-sub software.
- Two viable compute paths (Apalis now sidelined for this phase):
  - Jetson Orin Nano/NX companion on small-form-factor carrier like the [A603](https://www.seeedstudio.com/A603-Carrier-Board-for-Jetson-Orin-NX-Nano-p-5635.html) available from [Mouser](https://mou.sr/3Y31r4n)

---

## Cue Generation & Frame Alignment

### Problem
Given platform GPS/attitude and target GPS, produce a pixel-space cue in the active camera frame despite captive flight and unknown frame misalignments.

### Required Calibrations
1. Pixhawk → Gimbal DCM  
2. Gimbal → Camera/Gyro DCM  

### Work Items
- Explicit frame tree (Earth → Vehicle → Gimbal → Camera)
- Synchronized logging of Pixhawk attitude, gimbal encoders, camera observations
- Batch optimization to solve fixed DCMs

### Definition of Done
- Function: (GPS_p, GPS_t, attitude_p, gimbal_state) → (u, v)
- Quantified pixel error
- Repeatable, scriptable calibration procedure

### Status
A technical report has been written covering the theory for boths steps 1 and 2.  Code has been written to perform Step 2 of the calibration process, and tested with a simulation environment.

### Risks
There is considerable compliance in the gimbal dampening device, which may affect DCM calibration

---

## Camera Service
Implement Aravis container

## Web UI for Test & Configuration

### Purpose
Reduce iteration friction.

### Required Capabilities
- Live image display
- Overlay: detections, cues, tracks
- System status (FPS, latency)
- Config controls via ZMQ

### Definition of Done
- Single web page
- UI actions change system behavior

---

## Subsystem Architecture

### Working Rule
- Libraries: Python modules
- Live services: independent processes/containers
- Interfaces fixed via ZMQ + shared memory

### Definition of Done
- One-page architecture diagram
- No ambiguity on ownership or interfaces

---

## Image Augmentation

### Immediate Need
Simulate range and degradation effects without 3D scene generation.

### Augmentations
- Spatial scaling
- Pixelation / resampling
- Blur, haze, contrast loss
- Compression artifacts

### Definition of Done
- Scriptable augmentation pipeline
- Label-safe
- Measurable detector performance impact

---

## Sensor Calibration & Geometry

### Camera intrinsic calibration
- Extract and standardize intrinsic outputs from existing calibration container (K, distortion, image size, model).
- Ingest intrinsics into runtime system (cue projection, overlays, pixel↔angle math).
- Validate on live camera data that intrinsics are actually being applied.

### Body motion isolation calibration (real world)
- Define real-world calibration procedure based on existing theory and simulation.
- Collect captive-flight data (synchronized body IMU, payload gyro, gimbal encoders, image timestamps).
- Estimate isolation parameters from real data.
- Validate via reduced apparent target motion / improved track stability under known body motion.

---


## SOT timing integration with gyro propagation
- Add gyro message queue to SOT.
- Propagate SOT state:
  - on image arrival
  - between images using gyro updates.
- Enforce time guardrail:
  - tracker state must not advance more than Δt_max (≤0.5 s) ahead of latest confirmed sensor time.
- Validate with delayed/dropped image scenarios.

---

## CFT Platform Telemetry Integration

### High-bandwidth telemetry + video link (Doodle Labs)
- Select Doodle radio configuration for point-to-point captive use.
- Define Ethernet topology:
  - Doodle air radio ↔ seeker subsystem Ethernet.
- Bring up IP connectivity and run sustained throughput tests.
- Measure usable bandwidth and latency; document assumptions.

### Video transport over telemetry link
- Select video encoding (H.264 vs H.265).
- Select transport mechanism (RTP/UDP, GStreamer pipeline, etc.).
- Implement onboard encoding and streaming from camera.
- Implement ground-side decode and display.
- Measure end-to-end latency and stability over Doodle.

### Telemetry multiplexing over same link
- Define telemetry content:
  - seeker status
  - detections / tracks
  - cues
  - configuration commands.
- Define message transport (ZMQ over TCP/UDP).
- Verify coexistence with video under load.

### RC vs data-link separation
- Lock ELRS to RC control and gimbal/mode inputs.
- Lock Doodle to video, telemetry, and configuration.
- Ensure no functional dependency between the two links.

### Captive-flight downlink validation
- Run captive tests with live video and telemetry over Doodle.
- Verify latency and robustness during gimbal/body motion.
- Log link performance during runs.

---

## Guiding Principle

Each item must converge to a measurable result or be stopped.
