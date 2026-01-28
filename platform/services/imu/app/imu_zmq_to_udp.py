import os, json, zmq, socket

ZMQ_ENDPOINT = os.getenv("ZMQ_IMU_SUB", "tcp://127.0.0.1:5530")  # IMU PUB
UDP_IP = os.getenv("UDP_DST_IP", "127.0.0.1")
UDP_PORT = int(os.getenv("UDP_DST_PORT", "9100"))               # whatever client/gateway listens on

ctx = zmq.Context()
sub = ctx.socket(zmq.SUB)
sub.connect(ZMQ_ENDPOINT)
sub.setsockopt_string(zmq.SUBSCRIBE, "")  # all topics

udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

print(f"SUB {ZMQ_ENDPOINT}  ->  UDP {UDP_IP}:{UDP_PORT}", flush=True)

while True:
    topic, payload = sub.recv_multipart()
    # forward exactly what we publish today (topic + json payload)
    udp.sendto(topic + b" " + payload, (UDP_IP, UDP_PORT))
