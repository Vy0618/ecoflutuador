"""Detection values shared by the SSD and YOLO monitor adapters."""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Detection:
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2

    @property
    def centroid(self) -> Tuple[int, int]:
        x1, y1, x2, y2 = self.bbox
        return (x1 + x2) // 2, (y1 + y2) // 2


