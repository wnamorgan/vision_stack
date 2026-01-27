
import psutil, os, time
from datetime import datetime
from util.pub_sub import PubSub

class mon_sys(PubSub):
    def __init__(self, shutdown_event):
        self.shutdown_event = shutdown_event
        super().__init__()
        self.interval = 5.0
        self.name = "system_monitor"
        self.proc_map = {
            "dashboard": None,
            "gimbal": None,
            "seeker": None,
            "camera": None,
            "imu": None,
        }



    def run(self):
    
        # Initial process discovery by name
        parent = psutil.Process(os.getpid())

        for child in parent.children(recursive=True):
            try:
                pname = child.name()
                print(f"[DEBUG] child.name() = {pname}")
                if pname in self.proc_map:
                    self.proc_map[pname] = child
            except Exception:
                continue

        for proc in self.proc_map.values():
            if proc is not None and proc.is_running():
                proc.cpu_percent(interval=None)
    
        while not self.shutdown_event.is_set():
            cpu_percent = psutil.cpu_percent()
            virtual_mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            load_avg = psutil.getloadavg()
    
            processes = {}
            for pname, proc in self.proc_map.items():
                try:
                    if proc is not None and proc.is_running():
                        processes[pname] = {
                            "pid": proc.pid,
                            "cpu_percent": proc.cpu_percent(interval=0.1),
                            "mem_mb": proc.memory_info().rss / 1024 / 1024,
                        }
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
    
            # payload = {
            #     "name": "system_metrics",
            #     "type": "dashboard",
            #     "timestamp": datetime.utcnow().isoformat() + "Z",
            #     "system": {
            #         "cpu_percent": cpu_percent,
            #         "mem_total_mb": virtual_mem.total / 1024 / 1024,
            #         "mem_used_mb": virtual_mem.used / 1024 / 1024,
            #         "mem_percent": virtual_mem.percent,
            #         "swap_used_mb": swap.used / 1024 / 1024,
            #         "load_avg": list(load_avg),
            #     },
            #     "processes": processes,
            # }
            payload = {
                "name": "system_monitor",
                "type": "dashboard",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "per_process": [
                    {
                        "name": pname,
                        "pid": proc.pid,
                        "cpu_percent": proc.cpu_percent(interval=None),
                        "mem_mb": proc.memory_info().rss / 1024 / 1024,
                    }
                    for pname, proc in self.proc_map.items()
                    if proc is not None and proc.is_running()
                ],
                "system": {
                    "cpu_percent": cpu_percent,
                    "mem_total_mb": virtual_mem.total / 1024 / 1024,
                    "mem_used_mb": virtual_mem.used / 1024 / 1024,
                    "mem_percent": virtual_mem.percent,
                    "swap_used_mb": swap.used / 1024 / 1024,
                    "load_avg": list(load_avg),
                },
            }            
            msg = {
                "tx": self.name,
                "rx": "*",
                "topic": "health",
                "payload": payload
            }
            #print(msg['payload'])
            self.publish(msg)            

            time.sleep(self.interval)
