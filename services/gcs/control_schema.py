from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union, Dict, Any
import time


@dataclass
class ControlIntent:
    type: str
    value: Union[Dict[str, Any], str, int, None] = None
    t_backend: Optional[float] = None

    def normalize(self):
        self.t_backend = time.time()
        return self.__dict__
