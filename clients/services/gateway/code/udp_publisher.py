import os
import zmq
import socket
import json
import logging


"""
udp_publisher.py — Client uplink bridge (ZMQ -> UDP)

Reads JSON “intent” messages from the local ZMQ control bus (ZMQ_CONTROL),
serializes them, and sends them as UDP datagrams to the platform gateway
(UDP_DST_IP:UDP_DST_PORT). This isolates UDP transport details from the
HTTP/UI layer, so multiple local producers can share one uplink sender.
"""


ZMQ_PULL = os.getenv("ZMQ_CONTROL")
UDP_DST_IP = os.getenv("UDP_DST_IP")
UDP_DST_PORT = int(os.getenv("UDP_DST_PORT"))

def run():
    ctx = zmq.Context()
    sock = ctx.socket(zmq.PULL)
    sock.bind(ZMQ_PULL)

    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    log = logging.getLogger("api")
    logging.basicConfig(level=logging.INFO)
    while True:
        msg = sock.recv_json()
        log.info("[UDP_PUB] recv from ZMQ: %s", msg)
        log.info("[UDP_PUB] sendto %s:%d", UDP_DST_IP, UDP_DST_PORT)
        payload = json.dumps(msg).encode()
        udp.sendto(payload, (UDP_DST_IP, UDP_DST_PORT))
        print(f"[UDP] sent {msg}")
