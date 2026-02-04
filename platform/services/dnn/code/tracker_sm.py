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

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("tracker_sm")


class IntentType(str, Enum):
    TRACKER_RESET = "TRACKER_RESET"
    ACQ_ENABLE = "ACQ_ENABLE"


class TrackerStateMachine:
    def __init__(self, pub):
        self.state = TrackerState.IDLE
        self.acq_enabled = False
        self._lock = threading.Lock()
        self._pub = pub

    def publish_state(self):
        log.info("state=%s", self.state.value)
        self._pub.send_json(
            {"type": "TRACKER_STATE", "value": {"state": self.state.value, "ts": time.time()}}
        )

    def update_state(self, new_state: TrackerState):
        with self._lock:
            self.state = new_state
        self.publish_state()

    def reset(self):
        self.update_state(TrackerState.INIT)

    def set_acq_enable(self, enabled: bool = True):
        with self._lock:
            self.acq_enabled = bool(enabled)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "state": self.state.value,
                "acq_enabled": self.acq_enabled,
                "ts": time.time(),
            }


def run():
    ctx = zmq.Context()

    sub = ctx.socket(zmq.SUB)
    sub.connect(ZMQ_INTENT_SUB)
    sub.setsockopt_string(zmq.SUBSCRIBE, "")

    pub = ctx.socket(zmq.PUB)
    pub.bind(ZMQ_SM_PUB)

    sub_ego = ctx.socket(zmq.SUB)
    sub_ego.connect(ZMQ_EGO_SUB)
    sub_ego.setsockopt_string(zmq.SUBSCRIBE, "")

    sm = TrackerStateMachine(pub)

    def intent_loop():
        while True:
            msg = sub.recv_json()
            mtype = msg.get("type")
            if mtype == IntentType.TRACKER_RESET.value:
                sm.reset()
            elif mtype == IntentType.ACQ_ENABLE.value:
                sm.set_acq_enable(True)
                pub.send_json({"type": "TRACKER_STATUS", "value": sm.snapshot()})

    def ego_loop():
        while True:
            msg = sub_ego.recv_json()
            if msg.get("type") == "REF_LOCKED":
                sm.update_state(TrackerState.READY)

    threading.Thread(target=intent_loop, daemon=True).start()
    threading.Thread(target=ego_loop, daemon=True).start()

    period = 1.0 / max(0.1, HEARTBEAT_HZ)
    while True:
        pub.send_json({"type": "TRACKER_STATUS", "value": sm.snapshot()})
        time.sleep(period)
