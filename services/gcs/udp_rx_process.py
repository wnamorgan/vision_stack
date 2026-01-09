import os
import json
import time
import socket
import threading
import logging
from dataclasses import dataclass
from typing import Optional, List

import zmq


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("udp_rx")


@dataclass
class Binding:
    name: str
    port: int
    filter_type: Optional[str] = None


def _parse_bindings(s: str) -> List[Binding]:
    """
    UDP_RX_BINDINGS formats supported:

    1) Simple CSV:
       "meta:9100,control:9000"

    2) With filter:
       "meta:9100:FRAME_META,control:9000:RTP_SUBSCRIBE"

    3) JSON array:
       '[{"name":"meta","port":9100,"filter_type":"FRAME_META"}]'
    """
    s = (s or "").strip()
    if not s:
        raise ValueError("UDP_RX_BINDINGS is empty")

    # JSON array
    if s.startswith("["):
        arr = json.loads(s)
        out: List[Binding] = []
        for item in arr:
            out.append(
                Binding(
                    name=str(item["name"]),
                    port=int(item["port"]),
                    filter_type=item.get("filter_type"),
                )
            )
        return out

    # CSV
    out = []
    parts = [p.strip() for p in s.split(",") if p.strip()]
    for p in parts:
        fields = p.split(":")
        if len(fields) not in (2, 3):
            raise ValueError(f"Bad binding '{p}'. Use name:port or name:port:filter_type")
        name = fields[0].strip()
        port = int(fields[1])
        ftype = fields[2].strip() if len(fields) == 3 else None
        out.append(Binding(name=name, port=port, filter_type=ftype))
    return out


def run():
    # ZMQ PUB endpoint (single bus for all UDP streams)
    zmq_pub = os.getenv("ZMQ_PUB_ENDPOINT", "tcp://*:5570")

    # Multiple UDP ports supported
    bindings = _parse_bindings(os.getenv("UDP_RX_BINDINGS", "meta:9100:FRAME_META"))

    bind_host = os.getenv("UDP_RX_HOST", "0.0.0.0")
    max_dgram = int(os.getenv("UDP_RX_MAX_DGRAM", "65535"))

    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    pub.setsockopt(zmq.LINGER, 0)
    pub.setsockopt(zmq.SNDHWM, int(os.getenv("ZMQ_SNDHWM", "10")))
    pub.bind(zmq_pub)

    log.info("UDP RX online -> ZMQ PUB %s", zmq_pub)
    for b in bindings:
        log.info("  binding: name=%s udp=%s:%d filter_type=%s", b.name, bind_host, b.port, b.filter_type)

    def rx_loop(b: Binding):
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind((bind_host, b.port))
        while True:
            data, addr = udp.recvfrom(max_dgram)

            try:
                msg = json.loads(data.decode("utf-8"))
            except Exception:
                continue

            if not isinstance(msg, dict):
                continue

            if b.filter_type is not None and msg.get("type") != b.filter_type:
                continue

            # Tag the message so downstream can distinguish streams
            msg["_udp_src"] = b.name
            msg["_udp_port"] = b.port
            msg["_udp_from_ip"] = addr[0]
            msg["_udp_from_port"] = addr[1]
            msg["_udp_rx_ts"] = time.time()

            try:
                pub.send_json(msg, flags=zmq.NOBLOCK)
            except zmq.Again:
                # Drop if congested; this is a live stream adapter
                pass

    # One thread per port (simple + explicit)
    for b in bindings:
        threading.Thread(target=rx_loop, args=(b,), daemon=True).start()

    # Keep process alive
    while True:
        time.sleep(1)


if __name__ == "__main__":
    run()
