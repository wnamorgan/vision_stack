import cv2
import logging
import os
import time

from code.camera_base import Camera as BaseCamera
from code.aravis.camera import Camera as AravisCameraRaw
from code.aravis.utils.Image_from_Frame import frame_to_bgr


class AravisCamera(BaseCamera):
    def __init__(self, cam_args=None):
        self.cam_args = cam_args or {}
        self.cam = AravisCameraRaw(self.cam_args)
        self._chunk_info_period = float(os.getenv("INFO_PERIOD", "10.0"))
        self._chunk_last_log_t = time.time()
        self._pop_timeout_s = float(os.getenv("ARAVIS_POP_TIMEOUT_S", "0.5"))
        super().__init__()

    def start_capture(self):
        try:
            self.cam.start_acquisition_continuous()
        except Exception:
            logging.exception("Failed to start Aravis acquisition")
            raise
        super().start_capture()

    def stop_capture(self, unlink: bool = True):
        try:
            self.cam.stop_acquisition()
        except Exception:
            pass
        try:
            self.cam.shutdown()
        except Exception:
            pass
        super().stop_capture(unlink=unlink)

    def capture_frame(self):
        try:
            frame = self.cam.pop_frame(timeout_s=self._pop_timeout_s)
        except Exception:
            logging.exception("Aravis pop_frame failed")
            return False, None
        if frame is None:
            return False, None
        try:
            image = frame_to_bgr(self.cam, frame)
        finally:
            self.cam.push_frame(frame)

        if image is None:
            return False, None

        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

        h, w, c = image.shape
        metadata = {'h': h, 'w': w, 'c': c}
        if frame.has_chunks():
            chunk = self._extract_chunk_data(frame)
            if chunk:
                metadata.update(chunk)
                now = time.time()
                if now - self._chunk_last_log_t >= self._chunk_info_period:
                    logging.info("Chunk data: %s", chunk)
                    self._chunk_last_log_t = now
        return True, {'image': image, 'metadata': metadata}

    def _extract_chunk_data(self, frame):
        parser = getattr(self.cam, "chunk_parser", None)
        if parser is None:
            return None
        try:
            return {
                "timestamp": parser.get_integer_value(frame, "ChunkTimestamp"),
                "offset_x": parser.get_integer_value(frame, "ChunkOffsetX"),
                "offset_y": parser.get_integer_value(frame, "ChunkOffsetY"),
                "width": parser.get_integer_value(frame, "ChunkWidth"),
                "height": parser.get_integer_value(frame, "ChunkHeight"),
                "gain": parser.get_float_value(frame, "ChunkGain"),
                "exposure_time": parser.get_float_value(frame, "ChunkExposureTime"),
            }
        except Exception:
            logging.exception("Failed to parse chunk data")
            return None
