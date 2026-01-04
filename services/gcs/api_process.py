import os
import zmq
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
import logging
from typing import Optional

from control_schema import ControlIntent

CONTROL_API_PORT = int(os.getenv("CONTROL_API_PORT", "8100"))
ZMQ_PUSH = os.getenv("ZMQ_CONTROL")




class HelloReq(BaseModel):
    value: Optional[int] = 1


def run():
    ctx = zmq.Context()
    sock = ctx.socket(zmq.PUSH)
    sock.bind(ZMQ_PUSH)    
    app = FastAPI()

    @app.post("/control/hello")
    def hello(req: HelloReq):
        print("[API] sending intent to ZMQ")

        log = logging.getLogger("api")
        logging.basicConfig(level=logging.INFO)
        log.info("[API] handler entered")        
        intent = ControlIntent(type="HELLO", value=req.value)
        sock.send_json(intent.normalize())
        return {"status": "sent"}

    uvicorn.run(app, host="0.0.0.0", port=CONTROL_API_PORT)
