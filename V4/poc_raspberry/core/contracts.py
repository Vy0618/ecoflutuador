"""Model-independent contracts. Internal boxes remain xywh for compatibility."""
from dataclasses import dataclass
from typing import Protocol


@dataclass
class Detection:
    bbox: list[int]
    class_name: str
    confidence: float
    frame_id: int | None = None

    def to_result(self):
        x, y, w, h = self.bbox
        return {"class": self.class_name, "confidence": self.confidence,
                "bbox": [x, y, x+w, y+h], "center": [x+w/2, y+h/2],
                "frame_id": self.frame_id}


class DetectorBackend(Protocol):
    def detect(self, frame) -> list[Detection]: ...
