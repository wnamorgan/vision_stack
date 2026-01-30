import glob, os, time, logging, serial, threading
from collections import deque
from util.pub_sub import PubSub
from abc import ABC, abstractmethod

class SerialDevice(PubSub, ABC):
    """
    Generic serial-port device.

    Parameters
    ----------
    port : str | None
        Explicit /dev/tty* path.  If None, the class will try usb_id lookup.
    usb_id : dict | None
        Matching keys: {"vendor": "0c52", "product": "9020", "serial": "SLhD09Cs"}.
        Ignored if `port` is supplied.
    baudrate : int
    retry_s : float
        Seconds between retry attempts while waiting for the device.
    """

    def __init__(self, *, port: str | None = None,
                 usb_id: dict | None = None,
                 baudrate: int = 57600,
                 retry_s: float = 1.0):
        super().__init__()
        self.port      = port
        self.usb_id    = usb_id or {}
        self.baudrate  = baudrate
        self.retry_s   = retry_s

        self._rx_queue = deque()
        self._stop_event = threading.Event()
        self._reader_thread = None
        self._dispatcher_thread = None
        self.ser = None                      # will hold serial.Serial

    # ------------------------------------------------------------------ #
    # Public control                                                     #
    # ------------------------------------------------------------------ #
    def start(self):
        """Block until we locate and open the port, then launch threads."""
        self._block_until_port_ready()
        if self._stop_event.is_set():        # shutdown requested meanwhile
            return

        self.ser.flushInput()
        self._reader_thread = threading.Thread(target=self._read_serial, daemon=True)
        self._dispatcher_thread = threading.Thread(target=self._dispatch_messages,
                                                   daemon=True)
        self._reader_thread.start()
        self._dispatcher_thread.start()

    def stop(self):
        super().stop()
        self._stop_event.set()
        if self._reader_thread:
            self._reader_thread.join()
        if self._dispatcher_thread:
            self._dispatcher_thread.join()
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception as e:
            logging.warning("Error closing serial port: %s", e)
        self.ser = None            

    # ------------------------------------------------------------------ #
    # Port discovery / open                                              #
    # ------------------------------------------------------------------ #
    def _block_until_port_ready(self):
        warn_period_s = float(os.getenv("IMU_PORT_WARN_PERIOD", "5.0"))
        last_warn_t = 0.0
        while not self._stop_event.is_set():
            try:
                port_path = self.port or self.find_ttyusb()
                self.ser = serial.Serial(port_path, self.baudrate, timeout=1)
                logging.info("Connected to %s (baud %d)", port_path, self.baudrate)
                return
            except (serial.SerialException, FileNotFoundError, OSError) as exc:
                now = time.time()
                if now - last_warn_t >= warn_period_s:
                    logging.warning(
                        "Port not ready (%s); retrying in %.1fs",
                        exc,
                        self.retry_s,
                    )
                    last_warn_t = now
                time.sleep(self.retry_s)

    def _discover_port(self) -> str:
        """Return /dev/ttyUSB* path that matches self.usb_id; raise if none."""
        vid  = self.usb_id.get("vendor")
        pid  = self.usb_id.get("product")
        sn   = self.usb_id.get("serial")
        for sys_tty in glob.glob("/sys/class/tty/ttyUSB*"):
            path = os.path.realpath(os.path.join(sys_tty, "device"))
            parent = path
            for _ in range(3):
                probes = [os.path.join(parent, f) for f in
                          ("idVendor", "idProduct", "serial")]
                if all(os.path.isfile(p) for p in probes):
                    break
                parent = os.path.dirname(parent)

            def read_attr(name):
                try:
                    with open(os.path.join(parent, name)) as f:
                        return f.read().strip()
                except FileNotFoundError:
                    return None

            if (read_attr("idVendor")  == vid and
                read_attr("idProduct") == pid and
                read_attr("serial")    == sn):
                return "/dev/" + os.path.basename(sys_tty)

        raise FileNotFoundError("No USB-serial device matching "
                                f"{vid}:{pid} SN={sn} found")


    def find_ttyusb(self):
        """
        Scans /sys for all ttyUSB* devices, reads their USB attributes,
        and returns the matching /dev/ttyUSB* path (or None).
        """
        vendor   = self.usb_id.get("vendor")
        product  = self.usb_id.get("product")
        serial   = self.usb_id.get("serial")        
        for sys_tty in glob.glob("/sys/class/tty/ttyUSB*"):
            # # Resolve the device’s USB bus directory
            # devpath = os.path.realpath(os.path.join(sys_tty, "device"))
            # # Up one level usually lands in usbX/Y-1/
            # parent = os.path.dirname(devpath)
            
            # Follow the “device” symlink into the USB subtree
            path = os.path.realpath(os.path.join(sys_tty, "device"))
            # Climb up until we find our attribute files
            parent = path
            for _ in range(3):  # up to 3 levels
                if (os.path.isfile(os.path.join(parent, "idVendor"))
                 and os.path.isfile(os.path.join(parent, "idProduct"))
                 and os.path.isfile(os.path.join(parent, "serial"))):
                    break
                parent = os.path.dirname(parent)        
               
            
            attrs = {}
            for name in ("idVendor", "idProduct", "serial"):
                try:
                    with open(os.path.join(parent, name), "r") as f:
                        attrs[name] = f.read().strip()
                except FileNotFoundError:
                    attrs[name] = None
            print(f"[SerialDevice] Probing {sys_tty}")
            if (attrs.get("idVendor")  == vendor and
                attrs.get("idProduct") == product and
                attrs.get("serial")    == serial):
                # Build the /dev path
                self.set_latency_timer("/dev/" + os.path.basename(sys_tty))
                return "/dev/" + os.path.basename(sys_tty)
    
        #return None
        raise FileNotFoundError(
            f"No USB-serial device matching {vendor}:{product} SN={serial} found"
        )


    # ------------------------------------------------------------------ #
    # Message Dispatcher                                                 #
    # ------------------------------------------------------------------ #
    def _dispatch_messages(self):
        while not self._stop_event.is_set():
            if self._rx_queue:
                raw_msg = self._rx_queue.popleft()
                self.process(raw_msg)
            else:
                time.sleep(0.001)  # light sleep to reduce CPU usage


    def check_port(self) -> bool:
        if self.ser is None or not self.ser.is_open:
            return False
        try:
            self.ser.in_waiting  # triggers a read syscall under the hood
            return True
        except (serial.SerialException, OSError):
            return False
    
    def reconnect(self):
        """Force a full disconnect and reinitialization of the serial port."""
        print("[SerialDevice] Reconnect initiated")
        self.stop()
        self._stop_event.clear()
        self.start()

    def set_latency_timer(self, tty_dev, latency_ms=1):
        """Attempt to set FTDI latency timer for a given ttyUSB device."""
        dev_name = os.path.basename(tty_dev)
        latency_path = f"/sys/bus/usb-serial/devices/{dev_name}/latency_timer"
        try:
            with open(latency_path, 'w') as f:
                f.write(str(latency_ms))
            print(f"[info] Set latency_timer to {latency_ms} ms for {tty_dev}")
            return True
        except Exception as e:
            print(f"[warn] Failed to set latency_timer for {tty_dev}: {e}")
            return False
        
    # ------------------------------------------------------------------ #
    # Subclass hooks                                                     #
    # ------------------------------------------------------------------ #
    @abstractmethod
    def _read_serial(self): ...
    @abstractmethod
    def process(self, raw_message): ...
