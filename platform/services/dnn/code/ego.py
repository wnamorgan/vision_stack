import json
import os
import threading
import time

import zmq
import numpy as np

from code.states import TrackerState

ZMQ_CONNECT_SUB_SM_HOST = os.getenv("ZMQ_CONNECT_SUB_SM_HOST", "localhost")
ZMQ_CONNECT_SUB_SM_PORT = int(os.getenv("ZMQ_CONNECT_SUB_SM_PORT", "5580"))
ZMQ_SM_SUB = f"tcp://{ZMQ_CONNECT_SUB_SM_HOST}:{ZMQ_CONNECT_SUB_SM_PORT}"

ZMQ_BIND_PUB_EGO_HOST = os.getenv("ZMQ_BIND_PUB_EGO_HOST", "0.0.0.0")
ZMQ_BIND_PUB_EGO_PORT = int(os.getenv("ZMQ_BIND_PUB_EGO_PORT", "5581"))
ZMQ_EGO_PUB = f"tcp://{ZMQ_BIND_PUB_EGO_HOST}:{ZMQ_BIND_PUB_EGO_PORT}"

ZMQ_CONNECT_SUB_CAMERA_HOST = os.getenv("ZMQ_CONNECT_SUB_CAMERA_HOST", "camera")
ZMQ_CONNECT_SUB_CAMERA_PORT = int(os.getenv("ZMQ_CONNECT_SUB_CAMERA_PORT", "5555"))
ZMQ_CAMERA_SUB = f"tcp://{ZMQ_CONNECT_SUB_CAMERA_HOST}:{ZMQ_CONNECT_SUB_CAMERA_PORT}"

ZMQ_CONNECT_SUB_IMU_HOST = os.getenv("ZMQ_CONNECT_SUB_IMU_HOST", "imu")
ZMQ_CONNECT_SUB_IMU_PORT = int(os.getenv("ZMQ_CONNECT_SUB_IMU_PORT", "5530"))
ZMQ_IMU_SUB = f"tcp://{ZMQ_CONNECT_SUB_IMU_HOST}:{ZMQ_CONNECT_SUB_IMU_PORT}"

class EgoComp:
    def __init__(self):
        self._lock = threading.Lock()
        self._active = False
        self._state = TrackerState.IDLE
        self._last_ref_cam_ns = None
        self._last_ref_host_ns = None
        self._threads = []
        self._last_imu_host_ns = None
        self._dcm_tc = np.eye(3, dtype=np.float64)
        self._dcm_ic = np.eye(3, dtype=np.float64)  # TODO: set IMU->camera DCM

    def on_state(self, state: TrackerState):
        with self._lock:
            self._state = state
            if state == TrackerState.IDLE:
                self._active = False
                return
            if state == TrackerState.INIT:
                # Arm to freeze next camera frame.
                self._active = True
                return
            # READY/ACQ/TRACK: keep active.
            self._active = True

    def _tracker_loop(self):
        ctx = zmq.Context.instance()
        sub_sm = ctx.socket(zmq.SUB)
        sub_sm.connect(ZMQ_SM_SUB)
        sub_sm.setsockopt_string(zmq.SUBSCRIBE, "")
        while True:
            msg = sub_sm.recv_json()
            if msg.get("type") != "TRACKER_STATE":
                continue
            state_s = (msg.get("value") or {}).get("state")
            if not state_s:
                continue
            try:
                state = TrackerState(state_s)
            except Exception:
                continue
            self.on_state(state)

    def set_identity_on_init_frame(self, t_cam_hw_ns: int, t_host_hw_ns: int):
        with self._lock:
            self._last_ref_cam_ns = t_cam_hw_ns
            self._last_ref_host_ns = t_host_hw_ns
            self._dcm_tc = np.eye(3, dtype=np.float64)

    def _rodriguez(self, omega_rad: np.ndarray, dt_s: float) -> np.ndarray:
        theta = float(np.linalg.norm(omega_rad) * dt_s)
        if theta <= 0.0:
            return np.eye(3, dtype=np.float64)
        k = omega_rad / np.linalg.norm(omega_rad)
        kx, ky, kz = k
        k_skew = np.array(
            [[0.0, -kz, ky], [kz, 0.0, -kx], [-ky, kx, 0.0]],
            dtype=np.float64,
        )
        i3 = np.eye(3, dtype=np.float64)
        return i3 + np.sin(theta) * k_skew + (1.0 - np.cos(theta)) * (k_skew @ k_skew)

    def update_reference_frame(self, gyro_deg: np.ndarray, dt_s: float):
        if not self._active or dt_s <= 0.0:
            return
        gyro_rad = np.deg2rad(gyro_deg)
        omega_cam = self._dcm_ic @ gyro_rad
        r_tc = self._rodriguez(omega_cam, dt_s)
        with self._lock:
            self._dcm_tc = r_tc @ self._dcm_tc

    def normalize_dcm(self, thresh: float = 1e-3):
        with self._lock:
            if not self._active:
                return
            dcm = self._dcm_tc.copy()
        err = dcm.T @ dcm - np.eye(3, dtype=np.float64)
        if np.linalg.norm(err) < thresh:
            return
        q, _r = np.linalg.qr(dcm)
        with self._lock:
            self._dcm_tc = q

    def _camera_loop(self):
        ctx = zmq.Context.instance()
        sub_cam = ctx.socket(zmq.SUB)
        sub_cam.connect(ZMQ_CAMERA_SUB)
        sub_cam.setsockopt_string(zmq.SUBSCRIBE, "")
        pub = ctx.socket(zmq.PUB)
        pub.bind(ZMQ_EGO_PUB)
        while True:
            msg = sub_cam.recv_json()
            if msg.get("type") != "frame":
                continue
            md = msg.get("metadata") or {}
            t_cam_hw_ns = md.get("t_cam_hw_ns")
            t_host_hw_ns = md.get("t_host_hw_ns")
            if t_cam_hw_ns is None or t_host_hw_ns is None:
                continue
            with self._lock:
                state = self._state
            if state == TrackerState.INIT:
                self.set_identity_on_init_frame(int(t_cam_hw_ns), int(t_host_hw_ns))
                pub.send_json(
                    {
                        "type": "REF_LOCKED",
                        "value": {
                            "t_cam_hw_ns": int(t_cam_hw_ns),
                            "t_host_hw_ns": int(t_host_hw_ns),
                        },
                    }
                )

    def _imu_loop(self):
        ctx = zmq.Context.instance()
        sub_imu = ctx.socket(zmq.SUB)
        sub_imu.connect(ZMQ_IMU_SUB)
        sub_imu.setsockopt_string(zmq.SUBSCRIBE, "")
        while True:
            parts = sub_imu.recv_multipart()
            payload = parts[-1]
            try:
                msg = json.loads(payload.decode("utf-8"))
            except Exception:
                continue
            p = msg.get("payload") or {}
            gyro = p.get("gyro")
            t_host_hw_ns = p.get("t_host_hw_ns")
            if gyro is None or t_host_hw_ns is None:
                continue
            try:
                gyro_vec = np.array(gyro, dtype=np.float64)
            except Exception:
                continue
            with self._lock:
                last_ns = self._last_imu_host_ns
                self._last_imu_host_ns = int(t_host_hw_ns)
            if last_ns is None:
                continue
            dt_s = (int(t_host_hw_ns) - int(last_ns)) * 1e-9
            self.update_reference_frame(gyro_vec, dt_s)

    def run(self):
        self._threads = [
            threading.Thread(target=self._tracker_loop, daemon=True),
            threading.Thread(target=self._camera_loop, daemon=True),
            threading.Thread(target=self._imu_loop, daemon=True),
        ]
        for t in self._threads:
            t.start()
        while True:
            time.sleep(0.1)
            now = time.monotonic()
            if not hasattr(self, "_last_norm_s"):
                self._last_norm_s = now
                continue
            if now - self._last_norm_s >= 1.0:
                self._last_norm_s = now
                self.normalize_dcm()


def run():
    EgoComp().run()
