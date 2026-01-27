# class PubSub:
#     def __init__(self):
#         self._subscribers = []

#     def subscribe(self, callback):
#         """Register a callable to receive published messages."""
#         self._subscribers.append(callback)

#     def publish(self, message):
#         """Send message to all registered subscribers."""
#         for callback in self._subscribers:
#             try:
#                 callback(message)
#             except Exception as e:
#                 print(f"[PubSub] Error in subscriber: {e}")

import multiprocessing
import time
class PubSub:
    def __init__(self):
        self._subscribers = []

    def subscribe(self, queue: multiprocessing.Queue):
        """Register a queue to receive published messages."""
        self._subscribers.append(queue)

    def publish(self, message):
        """Send message to all registered subscriber queues."""
        for queue in self._subscribers:
            try:
                queue.put(message)
                #latency_ms = (time.time() - message['tov']) * 1000
                #print(f"[PubSub]: {latency_ms:6.1f} ms → {message['azDeg']}")                    
            except Exception as e:
                print(f"[PubSub] Error publishing to queue: {e}")

    def _inbox_loop(self):
        while not self._stop_event.is_set():
            try:
                msg = self._inbox.get(timeout=0.1)
                self.process_inbox(msg)
            except multiprocessing.queues.Empty:
                continue
            except Exception as e:
                print(f"[PubSub inbox error] {e}")

    def stop(self):
        pass
        # self._stop_event.set()
        # self._inbox_thread.join(timeout=2)

    #@abstractmethod
    def process_inbox(self, msg: dict):
        pass