import numpy as np
from multiprocessing import shared_memory

class SharedMemoryManager:
    _shm = None  # Static variable to hold the shared memory

    def __init__(self, shm_name="frame_shm", max_width=7680, max_height=4320, channels=3):
        self.shm_name = shm_name
        self.max_width = max_width
        self.max_height = max_height
        self.channels = channels
        self.shm_size = max_width * max_height * channels  # Maximum image size in bytes

        # If shared memory has not been created yet, create it
        if SharedMemoryManager._shm is None:
            SharedMemoryManager._shm = shared_memory.SharedMemory(create=True, name=self.shm_name, size=self.shm_size + 12)
            self.frame_data = np.ndarray((self.max_height, self.max_width, self.channels), dtype=np.uint8, buffer=SharedMemoryManager._shm.buf)
            self.metadata = np.ndarray((1, 3), dtype=np.int32, buffer=SharedMemoryManager._shm.buf)  # Store width, height, channels
        else:
            self.frame_data = np.ndarray((self.max_height, self.max_width, self.channels), dtype=np.uint8, buffer=SharedMemoryManager._shm.buf)
            self.metadata = np.ndarray((1, 3), dtype=np.int32, buffer=SharedMemoryManager._shm.buf)

    def write_metadata(self, width, height):
        """Write frame dimensions to metadata."""
        self.metadata[0, 0] = width
        self.metadata[0, 1] = height
        self.metadata[0, 2] = self.channels

    def write_frame(self, frame):
        """Write frame to shared memory."""
        height,width,depth = frame.shape
        self.write_metadata(width, height)
        np.copyto(self.frame_data[:height, :width, :], frame)

    def read_frame(self,width,height):
        return self.frame_data[:height, :width, :].copy()

    def cleanup(self):
        """Clean up shared memory."""
        if SharedMemoryManager._shm:
            SharedMemoryManager._shm.close()
            SharedMemoryManager._shm.unlink()
