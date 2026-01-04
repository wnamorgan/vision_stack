# Ground Control Station (GCS) UI Architecture Plan
---

## Executive Note: Image Transport Addendum (Why This Exists)

This document primarily defines the **end‑to‑end Ground Control Station (GCS) architecture**, including UI behavior, backend authority, command handling, and platform interaction.

The **Image Transport Semantics and Synchronization Addendum** was added after practical investigation showed that commonly assumed properties of UDP and RTP (frame identity, atomic delivery, reliable metadata association) **do not hold** in real systems once media decoders are involved.

This addendum exists to:
- Document **why RTP/JPEG cannot support firm frame↔metadata lock**
- Prevent future re‑litigation of this issue
- Clearly constrain how imagery may be used in control, fusion, and logging paths
- Justify the existence of an alternative transport option when correctness matters

Readers focused on UI, command, or platform control may skip the addendum.
Readers responsible for **imagery‑driven logic** must treat it as binding.


## 1. Introduction

This document describes a practical, production-aligned **Ground Control Station (GCS) architecture** for systems that stream live video, accept operator interaction, and exchange control/telemetry data over unreliable links.

The architecture intentionally separates **human-facing UI concerns** from **machine-facing transport concerns**, mirroring how real-world ISR, UAV, and robotics systems are built. The goal is robustness under packet loss, graceful behavior during link dropouts, and simplicity at the operator interface.

This design assumes:
- Live video over **UDP (RTP)**
- Operator interaction via a **browser-based UI**
- Side-channel telemetry and commands sent independently of video
- Tolerance for small timing skew between video and metadata

---

## 2. High-Level Architecture Overview

The system is divided into **three planes**, each with different requirements and protocols:

```
┌────────────┐      UDP/RTP       ┌──────────────┐      HTTP/TCP      ┌────────────┐
│  Platform  │ ─────────────────▶ │  GCS Backend │ ───────────────▶ │  Browser   │
│ (Vehicle)  │                    │ (Container)  │                  │   UI       │
└────────────┘                    └──────────────┘                  └────────────┘
        ▲                                  │
        └────────── UDP (Telemetry / Commands) ───────────────────────┘
```

---

## 3. Frontend vs Backend Responsibilities

### 3.1 Frontend (Browser UI)

**Responsibilities**
- Render live video frames
- Capture user input (mouse clicks, selections)
- Display telemetry and overlays

**Constraints**
- Cannot receive UDP or RTP
- Cannot run GStreamer
- Requires TCP-based protocols

**Protocols**
- HTTP (REST endpoints)
- Optional WebSockets (future)

**Key Principle**
> The browser never talks directly to the vehicle.

---

### 3.2 Backend (GCS Backend Container)

**Responsibilities**
- Terminate RTP video streams
- Decode video using GStreamer
- Drop stale frames to minimize latency
- Serve frames to the browser over HTTP
- Translate UI actions into platform commands

**Protocols**
- UDP/RTP (video in)
- UDP (telemetry & commands out/in)
- HTTP/TCP (UI)

This backend is effectively a **lightweight GCS**.

---

## 4. Video Plane (UDP / RTP)

### Why RTP over UDP
- Low latency
- Packet loss tolerance
- No backpressure during link dropouts
- Industry-standard for live video

### Key Design Choice
- Video is treated as **best-effort context**
- No attempt to embed frame identity or metadata into RTP
- Stale frames are dropped aggressively

### Ensuring “most recent frame”
- GStreamer appsink configured with:
  - `drop=true`
  - `max-buffers=1`
- Backend always serves the latest decoded frame
- Browser polling fetches current snapshot

---

## 5. Side-Channel Data (Telemetry & Ego State)

### Separation from Video
- Telemetry is **not synchronized at the packet level**
- Operator actions reference “what they see now”
- Small temporal skew is acceptable

### Practical Strategy
- Backend maintains latest telemetry state
- Browser requests telemetry on demand or periodically
- Ego-compensated views reduce sensitivity to skew

---

## 6. Command & Telemetry Plane (UDP / MAVLink)

### Why MAVLink Exists
MAVLink is a **UDP-based message protocol** designed for:
- Lossy links
- Stateless reconnection
- Message-level reliability

It sits *below* the UI layer.

---

### 6.1 MAVLink Command Semantics

Each command includes:
- `command_id`
- `target_system`
- `target_component`
- `confirmation`
- Optional parameters

#### ACK Handling
- Commands expecting confirmation use `COMMAND_ACK`
- Backend resends command if ACK not received within timeout

#### Duplicate Protection
- Commands include an ID/sequence
- Vehicle ignores duplicate execution
- Vehicle re-sends ACK if command already applied

---

### 6.2 Example: ACK and Retransmission

**Send Command**
```
COMMAND_LONG:
  command = MAV_CMD_DO_SET_MODE
  param1 = 4
```

**Vehicle Response**
```
COMMAND_ACK:
  command = MAV_CMD_DO_SET_MODE
  result = MAV_RESULT_ACCEPTED
```

**If ACK Lost**
- Backend resends command
- Vehicle detects duplicate
- Does NOT re-execute
- Sends ACK again

---

### 6.3 Example: NACK

```
COMMAND_ACK:
  command = MAV_CMD_DO_SET_MODE
  result = MAV_RESULT_DENIED
```

Backend:
- Stops retrying
- Surfaces error to operator

---

### 6.4 Custom MAVLink Command Example

**XML Definition**
```xml
<message id="42000" name="SET_IMAGE_POINT">
  <field type="uint32_t" name="frame_id"/>
  <field type="float" name="x"/>
  <field type="float" name="y"/>
</message>
```

**Generation**
- Add XML to MAVLink dialect
- Run `mavgen`
- Backend uses generated bindings

**Usage**
- Backend sends `SET_IMAGE_POINT`
- Vehicle correlates with its current state
- No image metadata required

---

## 7. UI Interaction Flow

1. Browser displays current frame
2. Operator clicks pixel (x, y)
3. Browser sends HTTP POST to backend
4. Backend translates to UDP command
5. Platform processes command
6. ACK flows back via telemetry

This mirrors real GCS behavior.

---

## 8. Dropouts and Link Loss

### Video
- Frames drop silently
- UI continues showing last frame
- No blocking

### Telemetry / Commands
- UDP-based
- Backend retries commands requiring ACK
- Stateless recovery after reconnection

### UI
- HTTP requests may fail temporarily
- Browser retries automatically
- No persistent connection required

---

## 9. Where Dash Fits (and Where It Doesn’t)

**Dash is a UI framework**, not a transport.

It:
- Runs over HTTP/TCP
- Is suitable for:
  - Layout
  - Controls
  - Visualization

It does **not**:
- Replace RTP
- Replace UDP telemetry
- Solve synchronization

Dash can sit entirely inside the **Frontend layer** if desired.

---

## 10. Key Takeaways

- This architecture matches real GCS / ISR systems
- Video, telemetry, and UI are intentionally decoupled
- UDP is used where loss is acceptable
- TCP is used where humans interact
- MAVLink solves message reliability, not UI concerns
- Exact frame/telemetry synchronization is unnecessary

This design scales, survives dropouts, and avoids brittle coupling.

---

## Image Transport Semantics and Synchronization (Addendum)

### Context and Scope
This addendum refines the **image transport discussion only** within the broader GCS architecture.
No other frontend, backend, command, or control narratives are altered.

---

## System Requirements (Binding)
Any image transport used within the GCS must support:

- Frame-atomic semantics (one image = one capture instant)
- Explicit frame identity and capture time
- Operation over intermittent / lossy data links
- Bounded latency (no unbounded blocking)
- Cross-platform compatibility (Yocto / Apalis, NVIDIA Jetson, desktop)
- Multiple consumers (local or remote UI backends)
- Detectable failure modes (dropped or degraded frames)
- No silent frame substitution for control or fusion use

---

## Critical Clarification: UDP vs RTP Decoder Semantics

UDP guarantees only best-effort packet delivery. Once RTP and a media decoder are involved:

- Decoders may repeat the last good frame
- Decoders may output partially reconstructed frames
- Loss may be concealed without notification
- A displayed image does not imply a new or complete frame was received

This behavior is intentional for visual continuity and explains why firm
frame-to-metadata synchronization cannot be enforced using RTP alone.

---

## Transport Options

### Option A — RTP/JPEG with UDP Side Channel (Best-Effort)

**Characteristics**
- Lowest steady-state latency
- Continues producing imagery during packet loss
- No recoverable frame identity at the consumer

**Synchronization Strategy (Probabilistic)**
- Producer-generated monotonic `frame_id` and `t_capture`
- One metadata packet per produced frame
- Temporal gating at the consumer (± one frame period)
- Explicit TRUSTED / UNTRUSTED / DROPPED frame states
- Optional TX_START / TX_END markers for confidence only

**Constraint**
This option must never be used for closed-loop control or fusion without
explicitly marking ambiguous frames.

---

### Option B — Application-Framed Images over SRT (Deterministic)

**Characteristics**
- Image and metadata delivered atomically
- Explicit integrity and completeness checks
- Bounded retransmission window

**Tradeoffs**
- Latency floor defined by ARQ window
- Fan-out may require relays or replication

---

## Why This Is Not Reinventing a Wheel

This design composes standard components across layers:

- Reliable UDP transports (SRT / RIST)
- Explicit application framing
- Sensor-style measurement semantics

Video ecosystems solve this using MPEG + KLV and accept latency.
Sensor systems assume reliable links.
No single standard spans both domains.

---

## Design Rule (Binding)

If the decoder is allowed to guess, the system must not pretend it knows.
---

## Appendix A — Image Transport Decision Summary

| Property | RTP/JPEG + Side Channel | SRT + Application‑Framed Images |
|--------|-------------------------|--------------------------------|
| Frame atomicity | ❌ No | ✅ Yes |
| Frame identity at consumer | ❌ Not recoverable | ✅ Explicit |
| Metadata binding | Probabilistic | Deterministic |
| Loss behavior | Conceal / repeat / partial | Drop or degrade explicitly |
| Silent substitution possible | ✅ Yes | ❌ No |
| Bounded latency | ✅ Yes | ✅ Yes (configurable) |
| Lowest steady‑state latency | ✅ | ❌ (slightly higher floor) |
| Suitable for visualization | ✅ | ✅ |
| Suitable for control / fusion | ❌ | ✅ |
| Implementation complexity | Low | Moderate |
| Cross‑platform viability | High | High |
| Industry precedent | Video streaming | Sensor / measurement transport |

**Interpretation**
- RTP/JPEG is appropriate only when **visual continuity** is more important than correctness.
- SRT framing is required when **frame identity and timing correctness** matter.

