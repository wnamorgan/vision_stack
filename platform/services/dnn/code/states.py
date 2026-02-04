from enum import Enum


class TrackerState(str, Enum):
    IDLE = "IDLE"
    INIT = "INIT"
    READY = "READY"
    ACQ = "ACQ"
    TRACK = "TRACK"
