# Integrated Detection, Acquisition, Tracking, and Operator Viewing — Best-of-Breed Design

**Document Version:** 1.0 (merged)  
**Date:** December 31, 2025

---

## 1. System Objective

Build an integrated perception + operator viewing system for long-range acquisition and tracking of small targets from a moving platform that:

- Maximizes **probability of acquisition** at long range (where targets are marginal).
- Transitions cleanly to **stable tracking** (SOT) once detection is reliable.
- Presents a **LOS-centric stabilized operator view** (software gimbal) without contaminating measurement/inference.
- Maintains strict separation between **measurement**, **inference**, **tracking**, and **visualization**.
- Runs feasibly on embedded platforms (e.g., **Orin Nano**) while performing DNN inference on the GPU.

**Design philosophy:** acquisition is probabilistic; short-term frame drops are acceptable if they increase detection probability.

---

## 2. Architectural Separation and Data Transport

### 2.1 Subsystem Separation (policy)
- **Measurement (camera):** produces images in **camera frame (c)**, time-stamped.
- **Inference (DNN):** consumes ROIs in **c** only; outputs detections as bounding boxes in **c**.
- **Tracking (SOT):** maintains track state in **earth/inertial frame (e)** (or in a consistent global frame), fusing detections and inertial data.
- **Visualization (operator):** renders a stabilized **viewing frame (v)** for human comprehension; overlays detections projected into **v**.

**No feedback path from v into measurement or inference.** Visualization artifacts must not alter inference semantics.

### 2.2 Data plane vs control plane
- **Bulk pixels:** shared memory (SHM).
- **Metadata/control:** ZeroMQ (ZMQ).

A practical contract (typical):
- SHM holds a fixed max-sized pixel buffer starting at byte 0.
- ZMQ message provides interpretation: `{shm_name, width, height, channels, frame_id, timestamp, optional pose}`.
- SHM is volatile state; metadata is authoritative for interpretation and synchronization.

---

## 3. Coordinate Frames (c, e, v) and Usage Policy

### 3.1 Frame definitions
- **c — Camera frame:** raw sensor coordinates. Images exist here. Inference happens here.
- **e — Earth/Inertial frame:** global frame used for LOS definition and track fusion.
- **v — Viewing frame:** synthetic operator-facing frame (virtual gimbal) used only for visualization.

### 3.2 Frame usage policy (non-negotiable)
- **Measurement:** only in **c**.
- **Inference:** only in **c**.
- **Operator intent & cueing:** only in **e**.
- **Visualization:** only in **v**.

---

## 4. Core Detection Philosophy

### 4.1 Problem framing
- Long-range targets occupy too few pixels to reliably activate detector feature maps.
- Global resize of full images destroys small-target evidence.
- Bandwidth/compute constraints force small ROIs during acquisition.
- At close range, targets can overfill ROIs, creating geometric ambiguity (interior features become preferable).

### 4.2 Core statement
**Single-scale inference** with **adaptive crop-and-upsample (local magnification)**, using **tiled ROIs during acquisition** to keep small targets above the detector’s minimum effective scale.

### 4.3 What this is NOT
- Not multi-scale inference (multiple scales per frame).
- Not super-resolution (no new information is created).
- Not track-before-detect.
- Not multiple competing models per frame.

---

## 5. Training and Validation Strategy (Scale-Aware)

### 5.1 Scale-aware augmentation (training extension)
Start with clean, close-range imagery and synthetically model far-range appearance:

1. Crop around the object (matching acquisition ROI sizes).
2. Downscale to simulate fewer pixels on target.
3. Apply mild blur and noise.
4. Upscale back to DNN input size (640).

Train on a mix:
- **Normal views** (tracking regime).
- **Synthetic far views** (acquisition regime).

### 5.2 Validation strategy
- Use real ground-based long-range imagery **only for validation** initially.
- If validation fails: adjust synthetic degradation (scale/noise/blur) until synthetic-to-real transfer is acceptable.

---

## 6. LOS-Centric Viewing Architecture (Operator)

### 6.1 Core concept
The invariant is the **line of sight (LOS)**, not the image.

- A target/ROI is defined in **e** (e.g., GPS coordinates or an inertial direction).
- Ownship pose is known.
- LOS is computed in **e** from ownship to ROI.
- Viewing frame **v** is defined so the LOS maps to the center of the operator display.

### 6.2 Synthetic track loop (“software gimbal”)
A synthetic track loop advances **v** toward the desired LOS with bounded angular authority so the LOS stays within camera FOV.

Inputs:
- Ownship position + attitude.
- ROI position (static or slowly varying).
- Camera extrinsics/pose `R_ce(t)`.

Outputs:
- Viewing orientation `R_ve(t)` (v relative to e).

Properties:
- Smooth motion, finite authority, no overshoot (policy).
- High-frequency body motion can be attenuated; low-frequency trajectory motion may be followed intentionally.

### 6.3 Rendering pipeline (viewer-only)
A common rotation-only rendering model:

- Relative rotation: `R_vc(t) = R_ve(t) · R_ce(t)^{-1}`
- Render a limited ROI around LOS in **v** by sampling from **c** using `R_vc`.

Notes:
- Rendering may include **stale pixel persistence** (optional) where regions temporarily outside the camera FOV remain from prior frames (viewer-only).
- Translation/parallax is not corrected by pure rotation; it may be mitigated later with optical flow or by operating at sufficient range.

### 6.4 Detection projection and overlay
Detections produced in **c** are projected for overlay in **v**:

- Convert pixel BB corners in **c** → rays (camera model) → rotate/transform through **e** → project into **v**.
- Result: operator sees detections aligned with stabilized view, with inertial meaning preserved.

---

## 7. Dynamic Image Scaling Policy (DNN vs Operator)

### 7.1 Hard constraint
- DNN input is fixed at **640×640**.

### 7.2 Operator scaling
- Operator view is rendered at **1080p** (typical).
- Operator scaling is fully decoupled from DNN scaling.
- The operator always sees a consistent window; internal resampling is a UI concern.

### 7.3 DNN scaling by phase (range / regime)
The DNN pipeline uses phase-dependent policies:

#### (A) Long-range acquisition / search
Goal: maximize detection probability for marginal targets.

- Use a small ROI centered on LOS uncertainty.
- Use **local magnification** so targets occupy more pixels at the DNN input.
- Use **tiling** to cover uncertainty without shrinking targets.

**Tiling options (policy-equivalent):**
1. **Upscale-then-tile** from a 640 ROI:
   - Start with a single 640 ROI.
   - Upscale to ~1152–1280.
   - Extract **4 overlapping 640 tiles** for DNN.
   - (Avoids extra resampling steps; simplest implementation.)
2. **Crop-larger-then-downscale** to guarantee full coverage with fixed overlap:
   - If targeting “10% overlap” while covering a larger logical ROI, crop ~**704×704** regions (per tile) and downscale to 640.
   - This guarantees overlap after resize without losing edges.

**Tradeoff:**
- Effective measurement update rate during tiling ≈ base DNN cadence / number of tiles (≈ /4).
- This is explicitly accepted during acquisition.

#### (B) Mid-range inspection / nominal
- Disable tiling.
- Extract a **single 640 ROI** centered on POI/LOS.
- Run DNN at full cadence.

#### (C) Close-range / tracking-dominant
- ROI scale decreases (<1×) as object fills pixels.
- DNN may be deprioritized (verification / reacquisition).
- Feature-level logic (markers) becomes preferred.

---

## 8. Acquisition-to-Tracking Transition (SOT)

### 8.1 Transition trigger
Upon consistent detections across N frames (and/or confidence thresholds):

- Initialize SOT with:
  - inertial LOS + image measurement,
  - timestamps and poses for correct association.

### 8.2 After lock
- Tiling is disabled.
- Tracking becomes the timeline owner (state evolution in **e**).
- DNN becomes secondary:
  - verify track,
  - reacquire if track quality drops,
  - detect interior marker when applicable.

---

## 9. Close-Range Target Switching (Marker Strategy)

Problem:
- At close range, the main object can overfill ROI; geometry becomes ambiguous.

Solution:
- Train two classes: **object** + **interior marker**.
- Allow nested labels.

Runtime logic:
1. Acquire/approach using object class.
2. When marker becomes reliable, **switch tracking state** to marker.
3. This is a state-based switch (no model conflict).

---

## 10. Parallelization and Performance Model

### 10.1 Parallel structure
- **Camera process:** free-running; publishes SHM + ZMQ metadata.
- **Inference process:** GPU-bound; consumes ROIs in c; policy-driven tiling during acquisition.
- **Viewer process:** CPU-bound; renders v; overlays detections.

### 10.2 Performance policy
- Frame drops are acceptable; stale frames are intentionally discarded.
- Optimize for **latency to first correct detection**, not constant throughput.
- Avoid unbounded queues; use bounded/latest semantics (drop old).

### 10.3 Feasibility on Orin Nano (qualitative)
- ROI-based inference reduces GPU load versus full-frame.
- Viewer rendering is lightweight relative to inference (especially at 1080p with rotation-only warps).
- Running at ~30 Hz operator view alongside DNN inference is feasible if:
  - tiling is limited to acquisition,
  - tracking reduces DNN duty cycle after lock,
  - CPU-side warps are kept bounded (or GPU-accelerated later if needed).

---

## 11. Assumptions, Applicability, and Risks

### 11.1 Explicit assumptions
- LOS remains within camera FOV (bounded synthetic gimbal authority).
- Ownship pose/time synchronization is adequate for projection.
- Viewer is for situational awareness; measurements come from **c**.
- Many uses assume scene near LOS is mostly stationary during short windows.

### 11.2 Known limitations and risks
**Acquisition (tiling):**
- Reduced temporal resolution during tiling may miss fast transients.
- Correlated tiles can increase false positives; aggregation/NMS must be consistent.

**Viewing (v):**
- Translation-induced parallax can smear if only rotation is compensated.
- Saturation of the synthetic gimbal can cause ROI to exit FOV.

**Mitigations (future):**
- Optical flow correction for translation (where needed).
- Mode gating/hysteresis to prevent oscillation.
- Clear fallback behaviors (viewer degrade only; inference remains unwarped).

---

## 12. Design Rationale (phased pipeline)
1. **Search aggressively when blind** (tiling + local magnification).
2. **Simplify once locked** (single ROI at full cadence).
3. **Exploit tracking when available** (SOT owns state; DNN verifies).
4. **Switch to interior marker** at close range for stable geometry.

---

## 13. One-Sentence Takeaway
You manage detectability by controlling how much of the scene is presented to a fixed-input DNN (local magnification + tiling during acquisition), transition to inertial tracking once detections stabilize, and render an LOS-centric stabilized operator view in a synthetic frame — all while keeping measurement and inference strictly in camera space.

