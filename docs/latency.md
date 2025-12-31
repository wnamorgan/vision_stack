# Latency Analysis: Serial vs Parallel Preprocess / Inference

This note documents latency and update-rate behavior for a camera → preprocess → inference pipeline, using simple timing assumptions and explicit definitions.

## Definitions

- Camera period: Tc = 1000 / 120 ≈ 8.33 ms
- Preprocessing time: Tp = 10 ms
- Inference time: Ti = 40 ms

Latency means capture → inference output.

Camera and compute are asynchronous; the age of the sampled camera frame is modeled as U[0, Tc], a uniformly distributed random variable accounting for phase mismatch.

## Case 1 — Serial execution (preprocess → inference)

Latency:
U[0, Tc] + Tp + Ti = U[0, 8.33] + 50 ms

Update period:
Tp + Ti = 50 ms

Camera asynchrony affects freshness, not cadence.

## Case 2 — Parallel, first frame during inference N used for N+1

Latency:
2Ti − U[0, Tc] = 80 − U[0, 8.33] ms

Update period:
Ti = 40 ms

Improves cadence but increases latency.

## Case 3 — Parallel, continuous preprocessing (overwrite-latest)

Latency:
Ti + Tp + U[0, 10] = 50 + U[0, 10] ms

Update period:
Ti = 40 ms

## Key takeaway

The minimum possible capture → result latency floor is Tp + Ti = 50 ms.
Parallelization improves update rate, not that floor.
Reducing latency below this requires changing or eliminating preprocessing.

## Implementation Plan — High-Cadence, CPU-Tolerant Pipeline (Current Assumption)

**Assumption:** update cadence is king until CPU limits are observed.

### Architecture
- **Shared memory (SHM):** camera writes continuously at sensor rate.
- **Three threads total (single process is fine initially):**
  1. Camera SHM → preprocess input queue
  2. Preprocessor
  3. DNN (inference)

### Queues
- **Camera → Preprocess queue**
  - Size = 1
  - Semantics: *latest frame only*
  - Writer overwrites if full (drop old, never block camera)

- **Preprocess → DNN queue**
  - Size = 1
  - Semantics: *latest preprocessed result*
  - Preprocessor overwrites if full

### Thread behavior
- **Camera copy thread**
  - Continuously copies latest camera SHM snapshot into queue (size 1)
  - Never blocks on consumers

- **Preprocessor thread**
  - Blocks on camera queue
  - Preprocesses frame immediately when available
  - Writes result to preprocess→DNN queue (overwrite semantics)

- **DNN thread**
  - Blocks on preprocess→DNN queue
  - Runs inference as soon as data is available
  - Defines system cadence (≈ Ti)

### Properties
- Update period ≈ **Ti**
- Latency ≈ **Tp + Ti + jitter**
- CPU may be overspent intentionally
- No backlog, no history chasing
- Old data is always discarded in favor of newest

### Exit criteria
- If CPU usage becomes problematic:
  - Revert to gated / one-lookahead preprocessing
  - Or reduce preprocess frequency
  - Or move preprocessing into GPU / inference graph