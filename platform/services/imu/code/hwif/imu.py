import time
import signal
import os
import psutil
import ctypes
from itertools import product
from hwif.imu_interface import IMUInterface  # adjust as needed
import logging

USB_VENDOR  = os.getenv("USB_VENDOR", "0403")
USB_PRODUCT = os.getenv("USB_PRODUCT", "6015")
USB_SERIAL  = os.getenv("USB_SERIAL", "D30FJZ4X")


class imu(IMUInterface):
    # Collect this information with the following bash command: udevadm info -q property -n /dev/ttyUSB0
    #usb_id = {"vendor": "0403", "product": "6015", "serial": "D30DQFRW"}  # update if needed
    usb_id = {"vendor": USB_VENDOR, "product": USB_PRODUCT, "serial": USB_SERIAL}
    uart_port = None#'/dev/ttyTHS1'
    def __init__(self, shutdown_event):
        self.shutdown_event = shutdown_event
        if False:
            super().__init__(usb_id=self.usb_id)
        else:
            super().__init__(port=self.uart_port, usb_id=self.usb_id)
        self.verbose = False
        self.initialized = False
        self.interval = 0.01
        self.log = logging.getLogger("imu")
        self.count = 0
    def run(self):
        # import setproctitle
        # setproctitle.setproctitle(self.name) 

        # import sys
        # sys.setswitchinterval(0.001)
        # self.start()
        # self.set_priority(priority=99)
        # time.sleep(0.1)

        signal.signal(signal.SIGINT, signal.SIG_IGN)


        while not self.shutdown_event.is_set() and not self.initialized:
            if self.verbose==True:
                self.log.info("Attempting initialization...")
            self.initialize()
            if not self.initialized:
                self.log.warning("Initialization failed - retrying in 1 second")
                time.sleep(1)

        while not self.shutdown_event.is_set():
            t0 = time.time()
            if self.initialized and (time.time() - self.t_last_received > 5):
                self.log.warning("No data in 5 seconds — resetting interface")
                self.reconnect()
                self.t_last_received = time.time()
                self.count = 0
            else:
                if self.low_rate:
                    self.aggregation_loop()
            t1 = time.time()
            dt = self.interval - (t1-t0)
            time.sleep( max(dt,self.interval/2.0) )
        #print("[IMU] Shutdown requested — stopping...")
        self.stop()
        #print("[IMU] Finished stop()")
        time.sleep(0.1)



    def aggregation_loop(self):
        with self.deque_lock:
            N = len(self.sample_deque)
            if N==0:
                return
            gyro  = [0.0, 0.0, 0.0]
            accel = [0.0, 0.0, 0.0]
            temp  = 0.0
            for payload in self.sample_deque:
                gyro  = [a+b for a,b in zip(gyro, payload['gyro'] )]
                accel = [a+b for a,b in zip(accel,payload['accel'])]
                temp  = temp + payload["temp"]
            self.sample_deque.clear()
        gyro  = [x/N for x in gyro]
        accel = [x/N for x in accel]
        temp  = temp/N
        self.count +=1
        timestamp = time.time() - self.t0
        msg = {
            "tx": self.name,
            "rx": "*",
            "topic": "gaa",
            "payload": {
                "timestamp": timestamp,
                "t_host_hw_ns": time.time_ns(),
                "gyro": gyro,
                "accel": accel,
                "counter": self.count,
                "temp": temp
            }
        }
        #print(f"[imu_interface] timestamp = ({msg['payload']['timestamp']}, {msg['payload']['counter']}, {N}, {temp})")
        self.publish(msg)
    


    def initialize(self): # placeholder 
        self.initialized=True

    def set_priority(self, priority=20):
        pid = os.getpid()
        proc = psutil.Process(pid)

        class SchedParam(ctypes.Structure):
            _fields_ = [("sched_priority", ctypes.c_int)]

        param = SchedParam(priority)
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        SCHED_FIFO = 1
        res = libc.sched_setscheduler(0, SCHED_FIFO, ctypes.byref(param))

        if res == 0:
            print(f"[imu] SCHED_FIFO set at priority {priority} (PID={pid})")
        else:
            err = ctypes.get_errno()
            print(f"[imu] sched_setscheduler failed: {os.strerror(err)}; falling back to nice")
            try:
                proc.nice(-20)
                print(f"[imu] nice(-20) set (PID={pid})")
            except psutil.AccessDenied:
                print(f"[imu] AccessDenied: cannot set nice for PID {pid}")
            except Exception as e:
                print(f"[imu] failed to nice(): {e}")
