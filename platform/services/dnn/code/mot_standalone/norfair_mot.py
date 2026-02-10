"""Minimal MOT wrapper for ego compensation experiments.

Usage:
    tracker = NorfairEgoTracker(distance_threshold=40, meas_prop="norfair")
    tracks, H_ref_from_cur = tracker.update(detections, H_cur_from_prev, H_ref_from_cur)

Inputs:
    detections: list[Detection] in current-frame (relative) pixel coords.
        Detection.points is an array shaped (n_points, 2) in pixels.
        Detection.scores is optional and should match n_points if provided.
    H_cur_from_prev: pixel-space homography for camera motion (K * dR * K^-1),
        mapping last-frame pixels -> current-frame pixels.
    H_ref_from_cur: pixel-space homography mapping current-frame pixels -> reference-frame pixels.

Outputs:
    tracks: list[TrackedObject] from Norfair. Each object exposes:
        - id/global_id: unique IDs (set once initialized)
        - estimate: current position estimate in *current/relative* frame
        - last_detection: last matched Detection (in absolute frame)
        - age, hit_counter, live_points, etc.
    H_ref_from_cur: updated cumulative current->reference transform.

Settings (and defaults):
    distance_threshold (float): max distance for matching detections to tracks. Required.
    initialization_delay (int): hit-counter threshold to mark a track as initialized.
        Tracks start at hit_counter=period, decrement by period each update,
        and increment by 2*period on each match. Default: 0 (show immediately).
    hit_counter_max (int): upper cap for hit_counter (controls persistence on misses).
        Default (Norfair): 15
    period (int): passed to Tracker.update; default is 1 in Norfair and used to
        scale hit-counter changes and the Kalman predict/update step.
"""

import numpy as np
from norfair import Detection, Tracker
from norfair.camera_motion import HomographyTransformation


def apply_h(pt, H):
    arr = np.asarray(pt, dtype=np.float64).ravel()
    if arr.size < 2 or not np.isfinite(arr[0]) or not np.isfinite(arr[1]):
        return None
    x, y = arr[0], arr[1]
    v = H @ np.array([x, y, 1.0], dtype=np.float64)
    if not np.isfinite(v[2]) or v[2] == 0:
        return None
    return (v[0] / v[2], v[1] / v[2])


class NorfairEgoTracker:
    def __init__(
        self,
        distance_threshold: float,
        initialization_delay: int = 0,
        meas_prop: str = "external",  # {none, norfair, external}
        hit_counter_max: int = 15,
    ):
        self._distance_threshold = distance_threshold
        self._initialization_delay = initialization_delay
        self._hit_counter_max = hit_counter_max
        self.init_tracker()
        self.meas_prop = meas_prop

    def init_tracker(self):
        self.tracker = Tracker(
            distance_function="euclidean",
            distance_threshold=self._distance_threshold,
            initialization_delay=self._initialization_delay,
            hit_counter_max=self._hit_counter_max,
        )

    def update(self, detections, H_cur_from_prev, H_ref_from_cur):
        # H_cur_from_prev maps last-frame pixels -> current-frame pixels.
        # H_ref_from_cur maps current-frame pixels -> reference-frame pixels (cumulative).
        # Maintain reference-frame transform (current -> reference).
        H_prev_from_cur = np.linalg.inv(H_cur_from_prev)
        H_ref_from_cur = H_ref_from_cur @ H_prev_from_cur

        if self.meas_prop == "none":
            tracks = self.tracker.update(detections=detections)
        elif self.meas_prop == "norfair":
            # Norfair expects abs->rel (reference -> current).
            H_cur_from_ref = np.linalg.inv(H_ref_from_cur)
            coord_T = HomographyTransformation(H_cur_from_ref.astype(np.float32))
            tracks = self.tracker.update(
                detections=detections, coord_transformations=coord_T
            )
        else:
            # External measurement propagation into reference frame (manual rel->abs).
            dets_ref = []
            for d in detections:
                p_ref = apply_h(d.points, H_ref_from_cur)
                if p_ref is None:
                    continue
                dets_ref.append(
                    Detection(
                        points=np.array([[p_ref[0], p_ref[1]]], dtype=np.float32),
                        scores=np.array([1.0], dtype=np.float32),
                    )
                )
            tracks = self.tracker.update(detections=dets_ref)

        return tracks, H_ref_from_cur
