"""Demo: compare Norfair ego-comp via internal vs external measurement propagation.

Key feature: toggle between
  - meas_prop="norfair": let Norfair convert detections (rel->abs) internally via coord_transformations
  - meas_prop="external": manually warp detections into the absolute/reference frame

This simulation projects a few fixed 3D points into the image under camera yaw,
then tracks them with/without ego compensation to show ID stability differences.
SPACE advances one step; Q quits.
"""

import argparse
import numpy as np
import cv2

from norfair import Detection

from norfair_mot import NorfairEgoTracker, apply_h


# Simple BGR color map for readability.
COLORS = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "red": (0, 0, 255),
    "green": (0, 255, 0),
    "blue": (255, 0, 0),
    "yellow": (0, 255, 255),
    "cyan": (255, 255, 0),
    "magenta": (255, 0, 255),
    "orange": (0, 128, 255),
    "purple": (128, 0, 255),
}

# ---------- Camera intrinsics ----------
K = np.array([[800.0, 0.0, 640.0],
              [0.0, 800.0, 360.0],
              [0.0,   0.0,   1.0]], dtype=np.float32)
Kinv = np.linalg.inv(K)

# ---------- 3 objects (unit vectors; "far field") ----------
world_pts = np.array([[0.00, 0.00, 1.0],
                      [0.06, 0.02, 1.0],
                      [-0.05, -0.03, 1.0]], dtype=np.float32)
world_pts /= np.linalg.norm(world_pts, axis=1, keepdims=True)


def rot_yaw(theta):
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, 0.0, s],
                     [0.0, 1.0, 0.0],
                     [-s, 0.0, c]], dtype=np.float32)


def project(R, pts):
    cam = (R @ pts.T).T
    cam = cam / cam[:, 2:3]
    pix = (K @ cam.T).T
    return pix[:, :2]


def dets_from_pix(pix, noise_px=2.0, drop_prob=0.15):
    dets = []
    for p in pix:
        if np.random.rand() < drop_prob:
            continue
        pn = p + np.random.randn(2).astype(np.float32) * noise_px
        dets.append(
            Detection(
                points=np.array([pn], dtype=np.float32),
                scores=np.array([1.0], dtype=np.float32),
            )
        )
    return dets


def _color_for_id(tid):
    # Deterministic vivid-ish palette
    palette = [
        COLORS["green"],
        COLORS["blue"],
        COLORS["red"],
        COLORS["cyan"],
        COLORS["magenta"],
        COLORS["yellow"],
        COLORS["orange"],
        COLORS["purple"],
    ]
    return palette[int(tid) % len(palette)]


def draw(frame, dets, tracks, trails=None, track_H=None):
    def to_py_ints(pt):
        arr = np.asarray(pt, dtype=np.float64).ravel()
        if arr.size < 2 or not np.isfinite(arr[0]) or not np.isfinite(arr[1]):
            return None
        return (int(np.rint(arr[0]).item()), int(np.rint(arr[1]).item()))

    h, w = frame.shape[:2]

    # detections (yellow)
    for d in dets:
        xy = to_py_ints(d.points)
        if xy is None:
            continue
        x, y = xy
        if x < -100 or y < -100 or x > w + 100 or y > h + 100:
            continue
        cv2.circle(frame, (x, y), 5, COLORS["yellow"], -1)

    # tracks (color by id)
    for t in tracks:
        est = t.estimate
        if track_H is not None:
            est = apply_h(est, track_H)
        xy = to_py_ints(est)
        if xy is None:
            continue
        x, y = xy
        if x < -100 or y < -100 or x > w + 100 or y > h + 100:
            continue
        color = _color_for_id(t.id)
        if trails is not None:
            trails.setdefault(t.id, []).append((x, y))
        cv2.circle(frame, (x, y), 8, color, 2)
        cv2.putText(frame, f"id={t.id}", (x + 10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    # trails on top
    if trails is not None:
        for tid, pts in trails.items():
            if len(pts) < 2:
                continue
            for i in range(1, len(pts)):
                cv2.line(frame, pts[i - 1], pts[i], _color_for_id(tid), 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--meas-prop",
        choices=["norfair", "external"],
        default="external",
        help="Measurement propagation method (norfair=internal, external=manual).",
    )
    args = parser.parse_args()

    np.random.seed(0)

    # Key knobs to make failure visible
    yaw_per_step = np.deg2rad(5.0)    # rotate per SPACE press
    dist_thresh = 40                  # looser association threshold (px)
    trail_len = 25
    meas_prop = args.meas_prop

    # Two trackers run side-by-side for comparison.
    tracker_no = NorfairEgoTracker(
        distance_threshold=dist_thresh,
        initialization_delay=0,
        meas_prop="none",
    )
    tracker_ego = NorfairEgoTracker(
        distance_threshold=dist_thresh,
        initialization_delay=0,
        meas_prop=meas_prop,
    )

    # Camera pose is a pure yaw rotation. R maps world -> camera frame.
    R = np.eye(3, dtype=np.float32)
    last_R = R.copy()
    # H_ref_from_cur maps current-frame pixels -> reference-frame pixels (cumulative).
    H_ref_from_cur = np.eye(3, dtype=np.float64)

    trails_no = {}
    trails_ego = {}
    last_ego_pos = {}

    # initialize first frame
    dets = []
    tracks_no = []
    tracks_ego = []
    img_no = np.zeros((720, 1280, 3), dtype=np.uint8)
    img_eg = np.zeros((720, 1280, 3), dtype=np.uint8)

    while True:
        # display current frame and wait for input
        cv2.imshow("NO_COMP", img_no)
        cv2.imshow("EGO_COMP", img_eg)
        key = cv2.waitKey(0) & 0xFF
        if key == ord("q"):
            break
        if key != ord(" "):
            continue

        # Incremental ego rotation per SPACE.
        R = rot_yaw(yaw_per_step) @ R

        pix = project(R, world_pts)
        dets = dets_from_pix(pix, noise_px=1.0, drop_prob=0.0)

        # Homography last->current (pixel-space projection of camera rotation).
        dR = R @ last_R.T
        H_cur_from_prev = K @ dR @ Kinv

        # Update trackers; H_ref_from_cur is updated internally (current -> reference).
        tracks_no, _ = tracker_no.update(dets, H_cur_from_prev, H_ref_from_cur)
        tracks_ego, H_ref_from_cur = tracker_ego.update(
            dets, H_cur_from_prev, H_ref_from_cur
        )
        last_R = R.copy()

        # visualize
        img_no = np.zeros((720, 1280, 3), dtype=np.uint8)
        img_eg = np.zeros((720, 1280, 3), dtype=np.uint8)
        # prune trail history
        for trails in (trails_no, trails_ego):
            for k in list(trails.keys()):
                if len(trails[k]) > trail_len:
                    trails[k] = trails[k][-trail_len:]

        draw(img_no, dets, tracks_no, trails_no)
        if meas_prop == "norfair":
            # Visualize where last tracks would move using the homography.
            for tid, p in list(last_ego_pos.items()):
                p2 = apply_h(p, H_cur_from_prev)
                xy = None if p2 is None else (int(np.rint(p2[0]).item()), int(np.rint(p2[1]).item()))
                if xy is None:
                    continue
                cv2.circle(img_eg, xy, 12, COLORS["white"], 2)  # predicted from last (larger)
                cv2.putText(img_eg, f"pred {tid}", (xy[0] + 8, xy[1] - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLORS["white"], 2)
            draw(img_eg, dets, tracks_ego, trails_ego)
            last_ego_pos = {t.id: t.estimate for t in tracks_ego}
        else:
            # External mode tracks live in reference frame; map back for display.
            H_cur_from_ref = np.linalg.inv(H_ref_from_cur)
            draw(img_eg, dets, tracks_ego, trails_ego, track_H=H_cur_from_ref)

        cv2.putText(img_no, "NO_COMP", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, COLORS["white"], 2)
        cv2.putText(img_eg, f"EGO_COMP ({meas_prop})", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, COLORS["white"], 2)
        cv2.putText(img_no, f"tracks={len(tracks_no)}  dets={len(dets)}", (20, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLORS["white"], 2)
        cv2.putText(img_eg, f"tracks={len(tracks_ego)}  dets={len(dets)}", (20, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLORS["white"], 2)
        cv2.putText(img_no, f"yaw_step_deg={np.rad2deg(yaw_per_step):.1f}", (20, 130),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLORS["white"], 2)
        cv2.putText(img_eg, f"yaw_step_deg={np.rad2deg(yaw_per_step):.1f}", (20, 130),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLORS["white"], 2)

        cv2.putText(img_eg, f"meas_prop={meas_prop}", (20, 160),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLORS["white"], 2)

        cv2.putText(img_no, "SPACE=step  Q=quit", (20, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLORS["white"], 2)
        cv2.putText(img_eg, "SPACE=step  Q=quit", (20, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLORS["white"], 2)

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
