import json
import os
import pathlib
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

ZMQ_CONNECT_SUB_INTENT_HOST = os.getenv("ZMQ_CONNECT_SUB_INTENT_HOST", "gateway")
ZMQ_CONNECT_SUB_INTENT_PORT = int(os.getenv("ZMQ_CONNECT_SUB_INTENT_PORT", "5560"))
ZMQ_INTENT_SUB = f"tcp://{ZMQ_CONNECT_SUB_INTENT_HOST}:{ZMQ_CONNECT_SUB_INTENT_PORT}"

class EgoComp:
    def __init__(self):
        self._lock = threading.Lock()
        self._active = False
        self._state = TrackerState.IDLE

        self._threads = []
        self._last_ego_ns       = None
        self.t_cam_hw_sw_offset = None
        self.gyro_rad           = None
        self.t0_ego_ns          = None
        self._DCM_T_from_C = np.eye(3, dtype=np.float64)
        self._DCM_C_from_I = np.eye(3, dtype=np.float64)  # default; overridden by calibration if present
        self._load_calibration()

        ctx = zmq.Context.instance()
        self.pub = ctx.socket(zmq.PUB)
        self.pub.bind(ZMQ_EGO_PUB)

    def on_state(self, state: TrackerState):
        with self._lock:
            self._state = state
            if state == TrackerState.IDLE:
                return
            if state == TrackerState.INIT:
                return

    def reset(self):
        with self._lock:
            self._active            = False
            self._last_ego_ns       = None
            self.t_cam_hw_sw_offset = None
            self.gyro_rad           = None
            self.t0_ego_ns          = None
            self._DCM_T_from_C = np.eye(3, dtype=np.float64)

    def _sm_loop(self):
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

    def _intent_loop(self):
        ctx = zmq.Context.instance()
        sub = ctx.socket(zmq.SUB)
        sub.connect(ZMQ_INTENT_SUB)
        sub.setsockopt_string(zmq.SUBSCRIBE, "")
        while True:
            msg = sub.recv_json()
            if msg.get("type") == "TRACKER_RESET":
                self.reset()

    def set_identity_on_init_frame(self, t_ego_ns: int):
        with self._lock:
            self.t0_ego_ns = t_ego_ns
            self._DCM_T_from_C = np.eye(3, dtype=np.float64)
            self._active = True

    def _load_calibration(self):
        path = os.getenv("CALIBRATION_PATH")
        if not path:
            return
        try:
            data = json.loads(pathlib.Path(path).read_text())
            DCM_C_from_I = data.get("imu", {}).get("DCM_C_from_I")
            if DCM_C_from_I is not None:
                self._DCM_C_from_I = np.array(DCM_C_from_I, dtype=np.float64)
        except Exception:
            pass

    @staticmethod
    def _rodrigues(omega_rad: np.ndarray, dt_s: float) -> np.ndarray:
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
        R_old_from_new = i3 + np.sin(theta) * k_skew + (1.0 - np.cos(theta)) * (k_skew @ k_skew)
        return R_old_from_new

    def update_reference_frame(self, dt_s: float):
        if not self._active or dt_s <= 0.0:
            return
        with self._lock:
            self._DCM_T_from_C = EgoComp.propagate_reference_frame(
                self._DCM_T_from_C, self._DCM_C_from_I, self.gyro_rad, dt_s
            )

    @staticmethod
    def propagate_reference_frame(
        DCM_T_from_C: np.ndarray,
        DCM_C_from_I: np.ndarray,
        gyro_I: np.ndarray, # radians
        dt_s: float,
    ) -> np.ndarray:
        omega_C = DCM_C_from_I @ gyro_I
        R_C_old_from_C_new = EgoComp._rodrigues(omega_C, dt_s)
        return DCM_T_from_C @ R_C_old_from_C_new

    def normalize_dcm(self, thresh: float = 1e-3):
        with self._lock:
            if not self._active:
                return
            dcm = self._DCM_T_from_C.copy()
        err = dcm.T @ dcm - np.eye(3, dtype=np.float64)
        if np.linalg.norm(err) < thresh:
            return
        q, _r = np.linalg.qr(dcm)
        with self._lock:
            self._DCM_T_from_C = q

    def _camera_loop(self):
        ctx = zmq.Context.instance()
        sub_cam = ctx.socket(zmq.SUB)
        sub_cam.connect(ZMQ_CAMERA_SUB)
        sub_cam.setsockopt_string(zmq.SUBSCRIBE, "")

        while True:
            msg = sub_cam.recv_json()
            if msg.get("type") != "frame" or self._active is False:
                continue
            md = msg.get("metadata") or {}
            t_cam_hw_ns = md.get("t_cam_hw_ns")
            t_cam_sw_ns = md.get("t_cam_sw_ns")
            if self.t_cam_hw_sw_offset is None: # TODO: Ideally this should be calibrated, for now, just latch a reasonable estimate of it
                self.t_cam_hw_sw_offset = t_cam_hw_ns - t_cam_sw_ns
            
            t_cam_sw_ns_est = t_cam_hw_ns - self.t_cam_hw_sw_offset
            with self._lock:
                last_ego_ns = self._last_ego_ns
                gyro_rad = self.gyro_rad

            if gyro_rad is None or last_ego_ns is None:
                continue

            dt_s = (int(t_cam_sw_ns_est) - int(last_ego_ns)) * 1e-9
            DCM_T_from_C = EgoComp.propagate_reference_frame(
                self._DCM_T_from_C, self._DCM_C_from_I, gyro_rad, dt_s
            )
            msg["DCM_T_from_C"] = DCM_T_from_C.tolist()
            msg["t_cam_sw_ns_est"] = int(t_cam_sw_ns_est)
            self.pub.send_json(msg)


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
            t_imu_sw_ns = p.get("t_imu_sw_ns")
            if gyro is None or t_imu_sw_ns is None:
                continue
            try:
                gyro_vec = np.array(gyro, dtype=np.float64)
            except Exception:
                continue
            if True: # Use System Clock as Time Base for Ego
                t_ego_ns = time.time_ns()
            else: # Use IMU SW Time Base for Ego
                t_ego_ns = int(t_imu_sw_ns)


            # Create the Tracker (Reference) Frame
            with self._lock:
                state = self._state
                active = self._active
            if state == TrackerState.INIT and not active:
                
                self.set_identity_on_init_frame(int(t_ego_ns))
                self.pub.send_json(
                    {
                        "type": "REF_LOCKED",
                        "value": {
                            "t0_ego_ns": int(self.t0_ego_ns),
                        },
                    }
                )

            # Propagate Tracker Frame
            with self._lock:
                last_ego_ns       = self._last_ego_ns
                self._last_ego_ns = t_ego_ns
                self.gyro_rad     = np.deg2rad(gyro_vec)    
            if last_ego_ns is None:
                continue
            dt_s = (int(t_ego_ns) - int(last_ego_ns)) * 1e-9
            self.update_reference_frame(dt_s)

    def run(self):
        self._threads = [
            threading.Thread(target=self._sm_loop,     daemon=True),
            threading.Thread(target=self._camera_loop, daemon=True),
            threading.Thread(target=self._imu_loop,    daemon=True),
            threading.Thread(target=self._intent_loop, daemon=True),
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
