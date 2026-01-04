import os
import time
import numpy as np
import threading

from .host_RTP import HostRTP

def rtp_tx_process():
    host = HostRTP()
    host.run()

def run():
    
    threading.Thread(target=rtp_tx_process, daemon=True).start()
    while True:
        time.sleep(1)
