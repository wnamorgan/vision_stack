import sys, os, subprocess
def set_usb_latency(device="ttyUSB0", latency="1"):
    path = f"/sys/bus/usb-serial/devices/{device}/latency_timer"
    if not os.path.exists(path):
        print(f"⚠️ Device path not found: {path}", file=sys.stderr)
        return
    try:
        # Use sudo tee so the redirection works as root
        subprocess.run(
            ["sudo", "tee", path],
            input=latency,
            text=True,
            check=True,
            stdout=subprocess.DEVNULL
        )
        print(f"Set {path} → {latency} ms")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Failed to set latency timer: {e}", file=sys.stderr)

import glob
import os



def find_ttyusb(vendor, product, serial):
    """
    Scans /sys for all ttyUSB* devices, reads their USB attributes,
    and returns the matching /dev/ttyUSB* path (or None).
    """
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

        if (attrs.get("idVendor")  == vendor and
            attrs.get("idProduct") == product and
            attrs.get("serial")    == serial):
            # Build the /dev path
            return "/dev/" + os.path.basename(sys_tty)

    return None


def setup_usb():
    # In Linux, you can identify the USB device properties using: udevadm info -q property -n /dev/ttyUSB2 (for something plugged into USB2)
    # Encode your adapter’s USB properties here:
    WANTED_VENDOR  = "0c52"
    WANTED_PRODUCT = "9020"
    WANTED_SERIAL  = "SLhD09Cs" 
    port = find_ttyusb(WANTED_VENDOR, WANTED_PRODUCT, WANTED_SERIAL)
    if port:
        print("Matched port:", port)
        set_usb_latency(device=port, latency="1")
    else:
        print("No matching USB-serial device found.")    
    
    return(port)
