import os
import threading

import zmq


def start_client_gw_udp_registration(*, name: str, port: int, logger) -> None:
    gw_cmd_push_host = os.getenv("ZMQ_CONNECT_PUSH_CLIENT_GW_CMD_HOST", "gateway")
    gw_cmd_push_port = int(os.getenv("ZMQ_CONNECT_PUSH_CLIENT_GW_CMD_PORT", "6010"))
    gw_cmd_sub_host = os.getenv("ZMQ_CONNECT_SUB_CLIENT_GW_CMD_HOST", "gateway")
    gw_cmd_sub_port = int(os.getenv("ZMQ_CONNECT_SUB_CLIENT_GW_CMD_PORT", "5575"))

    def _send_register(push):
        push.send_json({"type": "GW_REGISTER_UDP_BIND", "value": {"name": name, "port": port}})
        logger.info("Sent GW_REGISTER_UDP_BIND name=%s port=%d", name, port)

    def _heartbeat_loop():
        zctx = zmq.Context()
        sub = zctx.socket(zmq.SUB)
        sub.connect(f"tcp://{gw_cmd_sub_host}:{gw_cmd_sub_port}")
        sub.setsockopt_string(zmq.SUBSCRIBE, "")

        ctx = zmq.Context.instance()
        push = ctx.socket(zmq.PUSH)
        push.connect(f"tcp://{gw_cmd_push_host}:{gw_cmd_push_port}")

        while True:
            msg = sub.recv_json()
            if msg.get("type") != "GW_HEARTBEAT":
                continue
            val = msg.get("value") or {}
            bindings = val.get("udp_bindings") or []
            if not any(b.get("name") == name and b.get("port") == port for b in bindings):
                _send_register(push)

    threading.Thread(target=_heartbeat_loop, daemon=True).start()
