import os
import time
import threading
from enum import Enum

import zmq
import logging

from code.states import TrackerState
ZMQ_CONNECT_SUB_INTENT_HOST = os.getenv("ZMQ_CONNECT_SUB_INTENT_HOST", "gateway")
ZMQ_CONNECT_SUB_INTENT_PORT = int(os.getenv("ZMQ_CONNECT_SUB_INTENT_PORT", "5560"))
ZMQ_INTENT_SUB = f"tcp://{ZMQ_CONNECT_SUB_INTENT_HOST}:{ZMQ_CONNECT_SUB_INTENT_PORT}"

ZMQ_BIND_PUB_SM_HOST = os.getenv("ZMQ_BIND_PUB_SM_HOST", "0.0.0.0")
ZMQ_BIND_PUB_SM_PORT = int(os.getenv("ZMQ_BIND_PUB_SM_PORT", "5580"))
ZMQ_SM_PUB = f"tcp://{ZMQ_BIND_PUB_SM_HOST}:{ZMQ_BIND_PUB_SM_PORT}"

ZMQ_CONNECT_SUB_EGO_HOST = os.getenv("ZMQ_CONNECT_SUB_EGO_HOST", "localhost")
ZMQ_CONNECT_SUB_EGO_PORT = int(os.getenv("ZMQ_CONNECT_SUB_EGO_PORT", "5581"))
ZMQ_EGO_SUB = f"tcp://{ZMQ_CONNECT_SUB_EGO_HOST}:{ZMQ_CONNECT_SUB_EGO_PORT}"

HEARTBEAT_HZ = float(os.getenv("TRACKER_HEARTBEAT_HZ", "10"))

def env(name, default):
    return os.getenv(name, default)

class IntentType(str, Enum):
    TRACKER_RESET = "TRACKER_RESET"
    ACQ_ENABLE = "ACQ_ENABLE"


class TrackerStateMachine:
    def __init__(self, pub):
        self.state = TrackerState.IDLE
        self._lock = threading.Lock()
        self._pub = pub
        self.acq_enabled      = False
        self._reset_requested = False
        self._ref_locked      = False

        # logging
        self._last_log        = 0.0
        self.info_period = float(env("INFO_PERIOD", "3.0"))
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [SM] %(message)s",
        )
        self.log = logging.getLogger("Tracker (SM)")

    def publish_state(self):
        self.log.info("State = %s", self.state.value)
        self._pub.send_json(
            {"type": "TRACKER_STATE", "value": {"state": self.state.value, "ts": time.time()}}
        )

    def update_state(self, new_state: TrackerState):
        with self._lock:
            self.state = new_state
        self.publish_state()

    def reset(self):
        with self._lock:
            self.acq_enabled      = False
            self._reset_requested = False
            self._ref_locked      = False

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "state": self.state.value,
                "acq_enabled": self.acq_enabled,
                "ts": time.time(),
            }

    def intent_loop(self):
        ctx = zmq.Context.instance()
        sub = ctx.socket(zmq.SUB)
        sub.connect(ZMQ_INTENT_SUB)
        sub.setsockopt_string(zmq.SUBSCRIBE, "")
        while True:
            msg = sub.recv_json()
            mtype = msg.get("type")
            if mtype == IntentType.TRACKER_RESET.value:
                with self._lock:
                    self._reset_requested = True                
            elif mtype == IntentType.ACQ_ENABLE.value:
                with self._lock:
                    self.acq_enabled = bool(True)                

    def ego_loop(self):
        ctx = zmq.Context.instance()
        sub_ego = ctx.socket(zmq.SUB)
        sub_ego.connect(ZMQ_EGO_SUB)
        sub_ego.setsockopt_string(zmq.SUBSCRIBE, "")
        while True:
            msg = sub_ego.recv_json()
            if msg.get("type") == "REF_LOCKED":
                with self._lock:
                    self._ref_locked = True

    def transition_loop(self):
        period = 1.0 / 20.0  # 20 Hz
        while True:
            time.sleep(period)
            with self._lock:
                reset_req   = self._reset_requested
                ref_locked  = self._ref_locked
                acq_enabled = self.acq_enabled
                cur_state   = self.state

            if reset_req:
                self.reset()
                self.update_state(TrackerState.INIT)
            elif cur_state == TrackerState.INIT and ref_locked:
                self.update_state(TrackerState.READY)
            elif cur_state == TrackerState.READY and acq_enabled:
                self.update_state(TrackerState.ACQ)

            now = time.time()
            dt = now - self._last_log
            if dt >= self.info_period:
                self.log.info("State = %s | REF Locked = %s | ACQ Enabled = %s", cur_state.value, ref_locked, acq_enabled)
                self._last_log = now

def run():
    ctx = zmq.Context()

    pub = ctx.socket(zmq.PUB)
    pub.bind(ZMQ_SM_PUB)

    sm = TrackerStateMachine(pub)

    threading.Thread(target=sm.intent_loop, daemon=True).start()
    threading.Thread(target=sm.ego_loop, daemon=True).start()
    threading.Thread(target=sm.transition_loop, daemon=True).start()

    period = 1.0 / max(0.1, HEARTBEAT_HZ)
    while True:
        pub.send_json({"type": "TRACKER_STATUS", "value": sm.snapshot()})
        time.sleep(period)
