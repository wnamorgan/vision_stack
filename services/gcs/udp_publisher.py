import os
import zmq
import socket
import json

ZMQ_PULL = os.getenv("ZMQ_CONTROL")
UDP_DST_IP = os.getenv("UDP_DST_IP")
UDP_DST_PORT = int(os.getenv("UDP_DST_PORT"))

def run():
    ctx = zmq.Context()
    sock = ctx.socket(zmq.PULL)
    sock.connect(ZMQ_PULL)

    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    while True:
        msg = sock.recv_json()
        payload = json.dumps(msg).encode()
        udp.sendto(payload, (UDP_DST_IP, UDP_DST_PORT))
        print(f"[UDP] sent {msg}")
