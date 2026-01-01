#!/usr/bin/env python3
"""Entrypoint for the dashboard host RTP service."""

import signal
import logging
import sys
from pathlib import Path

# Ensure the package can be imported regardless of the working directory.
SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from code.host_RTP import HostRTP

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main():
    host = HostRTP()
    signal.signal(signal.SIGINT, host.signal_handler)
    signal.signal(signal.SIGTERM, host.signal_handler)
    host.run()


if __name__ == "__main__":
    main()
