# Detect and Track – Image Strategy & Detection Philosophy

## Problem Framing

- Small targets at long range are **marginal at first sighting** because they occupy too few pixels to reliably activate detector feature maps.
- Global resizing of full images destroys small-target evidence.
- Bandwidth constraints force **small ROIs**, especially during acquisition.
- At close range, targets can **overfill the ROI**, creating ambiguity; an interior feature can become the preferred tracking target.

---

## Detection Philosophy (Core Statement)

> **I’m doing single-scale inference with adaptive crop-and-upsample (local magnification), using tiled ROIs during acquisition to keep small targets above the detector’s minimum effective scale.**

Clarifications:
- This is **not multi-scale inference** (one inference pass per frame).
- This is **not super-resolution** (no new information is created).
- Scale is controlled by **how much of the raw image is cropped before resizing**.
- The “relative scale” that matters is **object size at the detector’s input grid**.

---

## Acquisition Strategy

- During far-range acquisition:
  - Use **small ROIs** centered on LOS uncertainty.
  - **Tile overlapping ROIs** to cover uncertainty without shrinking targets.
  - **Upsample each ROI** to the detector input size.
- This preserves small-target structure that would be lost under global resize.
- As confidence increases, collapse to fewer and/or larger ROIs.

---

## Training Data Extension (Scale-Aware Augmentation)

- Start with **clean, close-range imagery**.
- Synthetically extend it to model far-range appearance via:
  1. Crop around the object (matching acquisition ROI sizes).
  2. **Downscale** to simulate fewer pixels on target.
  3. Apply **mild blur and noise**.
  4. **Upscale back** to detector input size.

- This teaches the network to fire on weak, small-support targets presented via local magnification.
- Use a mix of:
  - normal views (tracking regime)
  - synthetic far views (acquisition regime)

---

## Validation Strategy

- Use **ground-based long-range imagery** *only for validation*.
- Do **not** train on it initially.
- Purpose:
  - Verify synthetic extensions accurately model real far-range behavior.

Outcomes:
- If validation passes → **green flag**.
- If validation fails → adjust synthetic degradation parameters (scale, noise, blur).

---

## Close-Range Behavior & Target Switching

- At close range, the main object can **overfill the ROI**, making geometry ambiguous.
- Introduce an **interior marker / feature** to break symmetry.

Detection setup:
- Two classes (e.g., object + marker).
- Overlapping / nested labels are allowed.

Runtime logic:
- Acquire and approach using the main object.
- When the interior marker is reliably detected, **switch tracking to it**.

This is a **state-based target switch**, not a class or model conflict.

---

## What This Is Not

- Not multi-scale inference.
- Not track-before-detect.
- Not super-resolution.
- Not multiple competing models per frame.

---

## One-Sentence Takeaway

You manage detectability by **controlling how much of the scene is presented to the network**, matching training to inference via **scale-aware augmentation**, and validating realism with **ground-truth far-range data** — all while keeping inference single-scale and deterministic.
