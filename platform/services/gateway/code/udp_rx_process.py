import os
import socket
import json
import zmq
import logging
UDP_RX_LISTEN_HOST = os.getenv("UDP_RX_LISTEN_HOST", "0.0.0.0")
UDP_RX_LISTEN_PORT = int(os.getenv("UDP_RX_LISTEN_PORT", "9000"))

class UDPListener:
    def __init__(self):
        
        self.listener_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.listener_socket.bind((UDP_RX_LISTEN_HOST, UDP_RX_LISTEN_PORT))
        print(f"Listening for UDP on port {UDP_RX_LISTEN_PORT}")

        self.zctx = zmq.Context()
        self.zpub = self.zctx.socket(zmq.PUB)
        host = os.getenv("ZMQ_BIND_PUB_INTENT_HOST", "0.0.0.0")
        port = int(os.getenv("ZMQ_BIND_PUB_INTENT_PORT", "5560"))
        self.zpub.bind(f"tcp://{host}:{port}")
        
        logging.basicConfig(level=logging.INFO)
        self.log = logging.getLogger("gateway")

        self.log.info("[GATEWAY] UDP RX ready on %s:%s", UDP_RX_LISTEN_HOST, UDP_RX_LISTEN_PORT)

    def listen(self):
        while True:
            msg, addr = self.listener_socket.recvfrom(1024)
            self.log.info("[GATEWAY] UDP recv %s from %s", msg, addr)
            print(f"Received message from {addr}: {msg}")
            try:
                data = json.loads(msg.decode('utf-8'))
                self.log.info("Forwarding UDP intent to ZMQ: %s", data)
                self.zpub.send_json(data)
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON: {e}")

def run():
    listener = UDPListener()
    listener.listen()
