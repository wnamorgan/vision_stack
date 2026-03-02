import json
import os
import socket
import threading

import zmq


def start_gateway_registration(*, endpoint: str, logger) -> None:
    """
    Start a heartbeat listener and (re)register endpoint with the gateway.
    """
    gw_ip = os.getenv("GW_INTENT_DST_IP", "gateway")
    gw_port = int(os.getenv("GW_INTENT_DST_PORT", "9000"))
    cmd_host = os.getenv("ZMQ_CONNECT_SUB_CMD_HOST", "gateway")
    cmd_port = int(os.getenv("ZMQ_CONNECT_SUB_CMD_PORT", "5561"))

    def _send_register():
        msg = {"type": "GW_REGISTER_ZMQ_SUB", "value": {"endpoint": endpoint}}
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(json.dumps(msg).encode("utf-8"), (gw_ip, gw_port))
            sock.close()
            logger.info("Sent GW_REGISTER_ZMQ_SUB to %s:%d endpoint=%s", gw_ip, gw_port, endpoint)
        except OSError as exc:
            logger.warning("Failed to send GW_REGISTER_ZMQ_SUB: %s", exc)

    def _heartbeat_loop():
        zctx = zmq.Context.instance()
        sub = zctx.socket(zmq.SUB)
        sub.connect(f"tcp://{cmd_host}:{cmd_port}")
        sub.setsockopt_string(zmq.SUBSCRIBE, "")
        while True:
            msg = sub.recv_json()
            if msg.get("type") != "GW_HEARTBEAT":
                continue
            val = msg.get("value") or {}
            endpoints = val.get("registered_endpoints") or []
            if endpoint not in endpoints:
                _send_register()

    threading.Thread(target=_heartbeat_loop, daemon=True).start()
    _send_register()
