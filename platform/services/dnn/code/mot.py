import os
import threading
import time
import json
from collections import deque

import zmq
import numpy as np
from norfair import Detection, Tracker

def apply_h(pt, H):
    arr = np.asarray(pt, dtype=np.float64).ravel()
    if arr.size < 2 or not np.isfinite(arr[0]) or not np.isfinite(arr[1]):
        return None
    x, y = arr[0], arr[1]
    v = H @ np.array([x, y, 1.0], dtype=np.float64)
    if not np.isfinite(v[2]) or v[2] == 0:
        return None
    return (v[0] / v[2], v[1] / v[2])

ZMQ_CONNECT_SUB_SM_HOST = os.getenv("ZMQ_CONNECT_SUB_SM_HOST", "localhost")
ZMQ_CONNECT_SUB_SM_PORT = int(os.getenv("ZMQ_CONNECT_SUB_SM_PORT", "5580"))
ZMQ_SM_SUB = f"tcp://{ZMQ_CONNECT_SUB_SM_HOST}:{ZMQ_CONNECT_SUB_SM_PORT}"

ZMQ_CONNECT_SUB_EGO_HOST = os.getenv("ZMQ_CONNECT_SUB_EGO_HOST", "localhost")
ZMQ_CONNECT_SUB_EGO_PORT = int(os.getenv("ZMQ_CONNECT_SUB_EGO_PORT", "5581"))
ZMQ_EGO_SUB = f"tcp://{ZMQ_CONNECT_SUB_EGO_HOST}:{ZMQ_CONNECT_SUB_EGO_PORT}"

ZMQ_CONNECT_SUB_DET_HOST = os.getenv("ZMQ_CONNECT_SUB_DET_HOST", "localhost")
ZMQ_CONNECT_SUB_DET_PORT = int(os.getenv("ZMQ_CONNECT_SUB_DET_PORT", "5566"))
ZMQ_DET_SUB = f"tcp://{ZMQ_CONNECT_SUB_DET_HOST}:{ZMQ_CONNECT_SUB_DET_PORT}"

ZMQ_BIND_PUB_MOT_HOST = os.getenv("ZMQ_BIND_PUB_MOT_HOST", "0.0.0.0")
ZMQ_BIND_PUB_MOT_PORT = int(os.getenv("ZMQ_BIND_PUB_MOT_PORT", "5582"))
ZMQ_MOT_PUB = f"tcp://{ZMQ_BIND_PUB_MOT_HOST}:{ZMQ_BIND_PUB_MOT_PORT}"

ZMQ_CONNECT_SUB_INTENT_HOST = os.getenv("ZMQ_CONNECT_SUB_INTENT_HOST", "gateway")
ZMQ_CONNECT_SUB_INTENT_PORT = int(os.getenv("ZMQ_CONNECT_SUB_INTENT_PORT", "5560"))
ZMQ_INTENT_SUB = f"tcp://{ZMQ_CONNECT_SUB_INTENT_HOST}:{ZMQ_CONNECT_SUB_INTENT_PORT}"

EGO_CACHE_MAX = int(os.getenv("MOT_EGO_CACHE_MAX", "10"))



class MOT:
    def __init__(self):
        """MOT worker with external measurement propagation."""
        self._dist_thresh = 40
        self._initialization_delay = 1
        self._hit_counter_max = 5
        self._init_tracker()
        self._lock = threading.Lock()
        self._tracker_state = None
        self._last_ego_msg = None
        self._last_match = None
        self._last_dets = None
        self._last_tracks = None
        self._threads = []
        self._ego_cache = deque(maxlen=EGO_CACHE_MAX)
        self._K = None
        self._Kinv = None
        self._last_H_ref_from_cur = None
        self._last_DCM_T_from_C = None
        self._last_t_cam_hw_ns = None
        self._last_t_cam_sw_ns = None
        self._last_t_cam_sw_ns_est = None
        self._load_calibration()
        ctx = zmq.Context.instance()
        self._mot_pub = ctx.socket(zmq.PUB)
        self._mot_pub.bind(ZMQ_MOT_PUB)

    def _init_tracker(self):
        self._tracker = Tracker(
            distance_function="euclidean",
            distance_threshold=self._dist_thresh,
            initialization_delay=self._initialization_delay,
            hit_counter_max=self._hit_counter_max,
        )

    def _load_calibration(self):
        path = os.getenv("CALIBRATION_PATH")
        if not path:
            return
        try:
            data = json.loads(open(path, "r", encoding="utf-8").read())
            K = data.get("camera", {}).get("K")
            if K is not None:
                self._K = np.array(K, dtype=np.float64)
                self._Kinv = np.linalg.inv(self._K)
        except Exception:
            pass

    def update(self, dets, H_ref_from_cur):
        dets_ref = []
        det_list = []
        for det_id, d in enumerate(dets):
            xyxy = d.get("xyxy")
            if not xyxy or len(xyxy) != 4:
                continue
            x1, y1, x2, y2 = xyxy
            cx = 0.5 * (x1 + x2)
            cy = 0.5 * (y1 + y2)
            p_ref = apply_h((cx, cy), H_ref_from_cur)
            if p_ref is None:
                continue
            dets_ref.append(
                Detection(
                    points=np.array([[p_ref[0], p_ref[1]]], dtype=np.float32),
                    scores=np.array([d.get("conf", 1.0)], dtype=np.float32),
                    data={"det_id": det_id},
                )
            )
            det_list.append(
                {"det_id": det_id, "xyxy": xyxy, "conf": float(d.get("conf", 1.0))}
            )
        tracks = self._tracker.update(detections=dets_ref)
        self._last_dets = det_list
        return tracks

    def _tracker_state_loop(self):
        ctx = zmq.Context.instance()
        sub = ctx.socket(zmq.SUB)
        sub.connect(ZMQ_SM_SUB)
        sub.setsockopt_string(zmq.SUBSCRIBE, "")
        while True:
            msg = sub.recv_json()
            if msg.get("type") != "TRACKER_STATE":
                continue
            state = (msg.get("value") or {}).get("state")
            with self._lock:
                self._tracker_state = state

    def _ego_loop(self):
        ctx = zmq.Context.instance()
        sub = ctx.socket(zmq.SUB)
        sub.connect(ZMQ_EGO_SUB)
        sub.setsockopt_string(zmq.SUBSCRIBE, "")
        while True:
            msg = sub.recv_json()
            frame_id = msg.get("frame_id")
            with self._lock:
                self._last_ego_msg = msg
                if frame_id is not None:
                    self._ego_cache.append((frame_id, msg))

    def _detections_loop(self):
        ctx = zmq.Context.instance()
        sub = ctx.socket(zmq.SUB)
        sub.connect(ZMQ_DET_SUB)
        sub.setsockopt_string(zmq.SUBSCRIBE, "")
        while True:
            msg = sub.recv_json()
            if msg.get("type") != "detections":
                continue
            frame_id = msg.get("frame_id")
            if frame_id is None:
                continue
            with self._lock:
                match = None
                for fid, ego_msg in self._ego_cache:
                    if fid == frame_id:
                        match = ego_msg
                        break
                if match is not None:
                    self._last_match = (msg, match)
                    self._last_t_cam_hw_ns = msg.get("t_cam_hw_ns")
                    self._last_t_cam_sw_ns = msg.get("t_cam_sw_ns")
                    self._last_t_cam_sw_ns_est = match.get("t_cam_sw_ns_est")
                    if self._K is not None and "DCM_T_from_C" in match:
                        dcm_tc = np.array(match["DCM_T_from_C"], dtype=np.float64)
                        self._last_DCM_T_from_C = dcm_tc
                        self._last_H_ref_from_cur = self._K @ dcm_tc @ self._Kinv
                        dets = msg.get("dets") or []
                        tracks = self.update(dets, self._last_H_ref_from_cur)
                        self._last_tracks = tracks
                        self._publish_tracks(frame_id, tracks)

    def _intent_loop(self):
        ctx = zmq.Context.instance()
        sub = ctx.socket(zmq.SUB)
        sub.connect(ZMQ_INTENT_SUB)
        sub.setsockopt_string(zmq.SUBSCRIBE, "")
        while True:
            msg = sub.recv_json()
            if msg.get("type") == "TRACKER_RESET":
                self.reset()

    def reset(self):
        with self._lock:
            self._tracker_state = None
            self._last_ego_msg = None
            self._ego_cache.clear()
            self._last_match = None
            self._last_H_ref_from_cur = None
            self._last_dets = None
            self._last_DCM_T_from_C = None
            self._last_tracks = None
            self._last_t_cam_hw_ns = None
            self._last_t_cam_sw_ns = None
            self._last_t_cam_sw_ns_est = None
        self._init_tracker()

    def _publish_tracks(self, frame_id, tracks):
        out_tracks = []
        for t in tracks:
            det_id = None
            last_det = getattr(t, "last_detection", None)
            if last_det is not None:
                det_id = (getattr(last_det, "data", {}) or {}).get("det_id")
            out_tracks.append(
                {
                    "track_id": t.id,
                    "estimate_T": t.estimate.tolist(),
                    "last_det_id": det_id,
                    "age": t.age,
                    "hit_counter": t.hit_counter,
                }
            )
        out = {
            "type": "tracks",
            "frame_id": frame_id,
            "source": "mot",
            "t_cam_hw_ns": self._last_t_cam_hw_ns,
            "t_cam_sw_ns": self._last_t_cam_sw_ns,
            "t_cam_sw_ns_est": self._last_t_cam_sw_ns_est,
            "DCM_T_from_C": (
                None
                if self._last_DCM_T_from_C is None
                else self._last_DCM_T_from_C.tolist()
            ),
            "K": (None if self._K is None else self._K.tolist()),
            "detections": self._last_dets or [],
            "tracks": out_tracks,
        }
        self._mot_pub.send_json(out)

    def run(self):
        self._threads = [
            threading.Thread(target=self._tracker_state_loop, daemon=True),
            threading.Thread(target=self._ego_loop,           daemon=True),
            threading.Thread(target=self._detections_loop,    daemon=True),
            threading.Thread(target=self._intent_loop,        daemon=True),
        ]
        for t in self._threads:
            t.start()
        while True:
            time.sleep(0.1)


def run():
    MOT().run()
