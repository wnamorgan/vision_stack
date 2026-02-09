import struct
import time
from collections import deque
from util.serial_device import SerialDevice  # adjust path as needed
import threading
import os

IMU_BAUD  = int(os.getenv("IMU_BAUD", "921600"))

class IMUInterface(SerialDevice):
    HEADER = b'\xAA\x55'
    HEADER_LEN = 2
    MAX_PAYLOAD_SIZE = 256
    GAA_ID = 0x8F

    def __init__(self, *, port=None, usb_id=None, baudrate=IMU_BAUD):
        super().__init__(port = port, usb_id=usb_id, baudrate=baudrate)
        self.name = "imu"
        self.rxCount = 0
        self.rxErrorCount = 0
        self.t_last_received = time.time()
        self.t0 = time.time()
        self.low_rate=False
        self.sample_deque = deque()
        self.deque_lock = threading.Lock()

    def _read_serial(self):
        buffer = bytearray()
        timestamp = None

        try:
            while not self._stop_event.is_set():
                data = self.ser.read(self.ser.in_waiting or 1)
                if data:
                    buffer.extend(data)

                while True:
                    header_pos = buffer.find(self.HEADER)
                    if header_pos == -1:
                        if len(buffer) > 1:
                            buffer = buffer[-1:]
                        timestamp = None
                        break
                    elif header_pos > 0:
                        buffer = buffer[header_pos:]

                    if len(buffer) < self.HEADER_LEN + 4:
                        break

                    if timestamp is None:
                        timestamp = time.time()

                    msg_len = buffer[4] + (buffer[5] << 8)
                    total_len = msg_len + self.HEADER_LEN

                    if total_len > self.MAX_PAYLOAD_SIZE + self.HEADER_LEN + 6:
                        buffer = buffer[self.HEADER_LEN:]
                        timestamp = None
                        continue

                    if len(buffer) < total_len:
                        break

                    packet = buffer[:total_len]
                    buffer = buffer[total_len:]

                    checksum_data = packet[2:-2]
                    checksum_recv = packet[-2] + (packet[-1] << 8)
                    if self.calc_checksum(checksum_data) != checksum_recv:
                        self.rxErrorCount += 1
                        timestamp = None
                        continue

                    self._rx_queue.append((packet, timestamp))
                    timestamp = None

        except Exception as e:
            print(f"[IMUInterface] Serial read error: {e}")
         

    def calc_checksum(self, data_bytes):
        return sum(data_bytes) & 0xFFFF

    def process(self, packet_with_time):
        packet, timestamp = packet_with_time
        data_id = packet[3]
        payload = packet[6:-2]

        if data_id != self.GAA_ID:
            return  # ignore non-GAA messages

        if len(payload) < 32:
            self.rxErrorCount += 1
            return


        try: 
            unpacked = struct.unpack('<6i3Hh', payload[:32])
            gyro  = [float(x) / 1e5 for x in unpacked[0:3]]   # deg/s
            accel = [float(x) / 1e6 for x in unpacked[3:6]]   # g
            counter = int(unpacked[6])
            usw     = int(unpacked[7])
            vinp    = float(unpacked[8]) / 100.0              # V
            temp    = float(unpacked[9]) / 10.0               # °C

            sample = {
                "timestamp": float(timestamp - self.t0),
                "t_imu_sw_ns": time.time_ns(),
                "gyro": gyro,          # list[float]
                "accel": accel,        # list[float]
                "counter": counter,    # int
                "usw": usw,            # int
                "vinp": vinp,          # float
                "temp": temp,          # float
            }

            if self.low_rate: # let child class deal with publishing
                with self.deque_lock:
                    self.sample_deque.append(sample)

            else: # publish high-rate data
                msg = {
                    "tx": self.name,
                    "rx": "*",
                    "topic": "gaa",
                    "payload": sample
                }
                #print(f"[imu_interface] timestamp = ({msg['payload']['timestamp']}, {msg['payload']['counter']})")
                self.publish(msg)
            self.rxCount += 1
            self.t_last_received = time.time()

        except Exception as e:
            print(f"[IMUInterface] GAA parse error: {e}")
            self.rxErrorCount += 1
