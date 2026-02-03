import os
import time
import threading
from enum import Enum

import zmq

ZMQ_CONNECT_SUB_INTENT_HOST = os.getenv("ZMQ_CONNECT_SUB_INTENT_HOST", "gateway")
ZMQ_CONNECT_SUB_INTENT_PORT = int(os.getenv("ZMQ_CONNECT_SUB_INTENT_PORT", "5560"))
ZMQ_INTENT_SUB = f"tcp://{ZMQ_CONNECT_SUB_INTENT_HOST}:{ZMQ_CONNECT_SUB_INTENT_PORT}"

ZMQ_BIND_PUB_TRACKER_HOST = os.getenv("ZMQ_BIND_PUB_TRACKER_HOST", "0.0.0.0")
ZMQ_BIND_PUB_TRACKER_PORT = int(os.getenv("ZMQ_BIND_PUB_TRACKER_PORT", "5580"))
ZMQ_TRACKER_PUB = f"tcp://{ZMQ_BIND_PUB_TRACKER_HOST}:{ZMQ_BIND_PUB_TRACKER_PORT}"

HEARTBEAT_HZ = float(os.getenv("TRACKER_HEARTBEAT_HZ", "10"))


class IntentType(str, Enum):
    TRACKER_RESET = "TRACKER_RESET"
    ACQ_ENABLE = "ACQ_ENABLE"


class TrackerState(str, Enum):
    IDLE = "IDLE"
    INIT = "INIT"
    READY = "READY"
    ACQ = "ACQ"
    TRACK = "TRACK"


class TrackerStateMachine:
    def __init__(self):
        self.state = TrackerState.IDLE
        self.acq_enabled = False
        self._lock = threading.Lock()

    def reset(self):
        with self._lock:
            self.state = TrackerState.INIT

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
    pub.bind(ZMQ_TRACKER_PUB)

    sm = TrackerStateMachine()

    def intent_loop():
        while True:
            msg = sub.recv_json()
            mtype = msg.get("type")
            if mtype == IntentType.TRACKER_RESET.value:
                sm.reset()
            elif mtype == IntentType.ACQ_ENABLE.value:
                sm.set_acq_enable(True)
                pub.send_json({"type": "TRACKER_STATUS", "value": sm.snapshot()})

    threading.Thread(target=intent_loop, daemon=True).start()

    period = 1.0 / max(0.1, HEARTBEAT_HZ)
    while True:
        pub.send_json({"type": "TRACKER_STATUS", "value": sm.snapshot()})
        time.sleep(period)
