# ANSI color codes
RED   = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"

import time

def disp_latency(tov):
    latency_ms = (time.time() - tov) * 1000
    if latency_ms > 50:
        latency_str = f"{RED}{latency_ms:6.1f}{RESET}"
    elif latency_ms > 30:
        latency_str = f"{YELLOW}{latency_ms:6.1f}{RESET}"                    
    else:
        latency_str = f"{GREEN}{latency_ms:6.1f}{RESET}"
    return latency_str 