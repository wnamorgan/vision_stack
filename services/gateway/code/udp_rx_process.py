import os
import socket
import json
import zmq

UDP_LISTEN_IP = os.getenv("UDP_LISTEN_IP", "0.0.0.0")
UDP_LISTEN_PORT = int(os.getenv("UDP_LISTEN_PORT", "9000"))

class UDPListener:
    def __init__(self):
        
        self.listener_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.listener_socket.bind((UDP_LISTEN_IP, UDP_LISTEN_PORT))
        print(f"Listening for UDP on port {UDP_LISTEN_PORT}")

        import logging
        logging.basicConfig(level=logging.INFO)
        self.log = logging.getLogger("gateway")

        self.log.info("[GATEWAY] UDP RX ready on %s:%s", UDP_LISTEN_IP, UDP_LISTEN_PORT)

    def listen(self):
        while True:
            msg, addr = self.listener_socket.recvfrom(1024)
            self.log.info("[GATEWAY] UDP recv %s from %s", msg, addr)
            print(f"Received message from {addr}: {msg}")
            try:
                data = json.loads(msg.decode('utf-8'))
                print(f"Control intent received: {data}")
                # Add logic here to forward intent to control handler
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON: {e}")

def run():
    listener = UDPListener()
    listener.listen()
