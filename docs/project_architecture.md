# vision_stack

## 1. Overview

`vision_stack` is the **deployment and integration repository** for the vision system.  
It composes cameras, trackers, gimbals, IMUs, and dashboards into a running system using **Docker Compose**, **ZeroMQ**, and **shared memory**.

This repo is **not** for training models or labeling data.  
Those live elsewhere (e.g. `embedded_vision`, `vision_lab`).

The goal here is:
- consistent runtime behavior across **lab**, **captive**, and **flight**
- strict interface contracts
- minimal refactoring when moving from simulation to real flight software

---

## 2. Directory Structure

```
vision_stack/
├─ docker-compose.yml
├─ README.md
├─ .env.example

├─ common/
│  ├─ zmq/
│  │  ├─ topics.md          # authoritative topic list
│  │  └─ schemas/           # message schemas / pydantic models
│  └─ shm/
│     └─ layout.md          # shared-memory frame layout

├─ services/
│  ├─ camera_aravis/
│  ├─ imu/
│  ├─ gimbal_gremsy/
│  ├─ tracker/
│  ├─ dashboard/
│  └─ flight_iface_sim/

├─ configs/
│  ├─ lab.yaml
│  ├─ captive.yaml
│  └─ flight.yaml

└─ scripts/
   ├─ up.sh
   └─ down.sh
```

**Rule:** anything runnable is a **service**.  
**Rule:** anything shared is a **contract**, not an implementation.

---

## 3. Design Summary

### 3.1 Why Docker Compose

- Defines **what runs**, not how it behaves
- Cleanly supports multiple deployment modes via **profiles**
- Lets each hardware-facing component live in its own dependency sandbox
- Avoids a growing Python monolith with fragile imports

Compose is the *system orchestrator*.

---

### 3.2 Why ZeroMQ + Shared Memory

- **ZeroMQ**
  - clear pub/sub contracts
  - easy replacement of publishers (sim vs real)
  - container- and machine-agnostic
- **Shared Memory**
  - avoids copying large image buffers
  - camera writes frames once
  - tracker reads by reference

**Rule:**  
> metadata over ZMQ, pixels over SHM.

---

### 3.3 Contracts and Compatibility

All downstream services assume:
- the **same topics**
- the **same schemas**
- regardless of whether data comes from:
  - a real flight computer
  - a captive platform
  - a simulated lab publisher

Only the **publisher changes** — consumers do not.

---

## 4. Runtime Concepts

### 4.1 Profiles

Profiles determine **which containers run**.

Examples:
- `lab`
- `captive`
- `flight`

Profiles do *not* change behavior — configs do.

---

### 4.2 YAML Configs

YAML files determine **how services behave**:
- endpoints
- rates
- enabled features
- logging level

Passed to services via:
```
CONFIG=lab.yaml
```

---

### 4.3 Services

Each service:
- owns **one responsibility**
- publishes and/or subscribes to topics
- has no knowledge of who else is running

---

## 5. Profiles

### 5.1 Flight Profile

**Intent:** integrate with real flight software.

**Assumptions:**
- Flight SW owns Pixhawk, IMU, GPS
- Flight SW publishes navigation and IMU topics over ZMQ

**Containers started:**
- camera_aravis
- tracker
- gimbal_gremsy
- (optional) recorder

**Containers NOT started:**
- imu
- flight_iface_sim
- dashboard (typically)

**External requirements:**
- system must publish:
  - `imu.data`
  - `nav.solution`
  - `cue.request` (or equivalent)

**Run:**
```bash
CONFIG=flight.yaml docker compose --profile flight up
```

---

### 5.2 Captive Profile

**Intent:** hardware-in-the-loop without full flight SW.

**Containers started:**
- imu
- camera_aravis
- tracker
- gimbal_gremsy
- flight_iface_sim
- dashboard

**Responsibilities:**
- `imu` reads physical IMU and publishes `imu.data`
- `flight_iface_sim`:
  - forms cues from Pixhawk GPS or test inputs
  - publishes acquisition commands

**Run:**
```bash
CONFIG=captive.yaml docker compose --profile captive up
```

---

### 5.3 Lab Profile

**Intent:** algorithm development and debugging.

**Containers started:**
- imu (or replay source)
- camera_aravis (or replay)
- tracker
- flight_iface_sim
- dashboard

**Responsibilities:**
- simulate what flight SW would publish
- keep contracts identical to flight

**Run:**
```bash
CONFIG=lab.yaml docker compose --profile lab up
```

---

## 6. Topics

### 6.1 Topic Inventory

This codebase uses topics such as:
- `camera.frames`
- `imu.data`
- `nav.solution`
- `cue.request`
- `track.state`
- `gimbal.command`

(Exact schemas live elsewhere.)

---

### 6.2 Topic Definitions

Authoritative definitions are in:
```
common/zmq/topics.md
```

**Rule:**  
> if it’s not in `topics.md`, it’s not a real interface.

---

## 7. How to Run

### 7.1 Common Commands

```bash
docker compose ps
docker compose logs -f tracker
docker compose down
```

---

### 7.2 Typical Workflows

- Lab debug → `lab` profile
- Captive carry → `captive` profile
- Integration with flight SW → `flight` profile

---

## 8. Development Notes

### 8.1 Logging and Debugging
- each service logs independently
- ZMQ messages include timestamps and source IDs

### 8.2 Recording / Replay
- recorder service can subscribe to all topics
- enables deterministic replay in lab

### 8.3 Model Versioning
- tracker loads models via config
- models are mounted, not built into images

---

## 9. Roadmap

- tighten schemas
- formalize replay
- reduce container count for flight-min build

---

## 10. Troubleshooting

- two publishers on one topic = misconfigured profile
- missing data = wrong endpoint in config
- schema mismatch = contract drift
