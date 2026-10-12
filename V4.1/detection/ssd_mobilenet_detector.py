"""Detector SSD MobileNet TensorFlow compatível com o tracker existente."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

import cv2
import numpy as np

from .types import Detection


# IDs COCO do SSD MobileNet. Para reconhecer as cinco classes do projeto, use
# um modelo treinado com elas e informe labels.txt com linhas "id nome".
class SsdMobileNetDetector:
    def __init__(
        self,
        model_path: str | Path,
        config_path: str | Path,
        labels_path: str | Path,
        confidence_threshold: float,
        input_width: int,
        input_height: int,
        allowed_classes: Iterable[str],
    ) -> None:
        model_file = Path(model_path)
        config_file = Path(config_path)
        if not model_file.is_file() or not config_file.is_file():
            raise FileNotFoundError(
                "Modelo SSD MobileNet ausente. Configure model_path e config_path "
                "com o .pb e .pbtxt compatíveis."
            )
        self.net = cv2.dnn.readNetFromTensorflow(str(model_file), str(config_file))
        self.confidence_threshold = confidence_threshold
        self.input_width = input_width
        self.input_height = input_height
        self.allowed_classes = set(allowed_classes)
        self.labels = self._load_labels(Path(labels_path))

    @staticmethod
    def _load_labels(path: Path) -> dict[int, str]:
        labels: dict[int, str] = {}
        for index, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            possible_id, separator, name = line.partition(" ")
            if separator and possible_id.isdigit():
                labels[int(possible_id)] = name.strip()
            else:
                labels[index] = line
        return labels

    def detect(self, frame: np.ndarray) -> List[Detection]:
        height, width = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(
            frame,
            scalefactor=1 / 127.5,
            size=(self.input_width, self.input_height),
            mean=(127.5, 127.5, 127.5),
            swapRB=True,
            crop=False,
        )
        self.net.setInput(blob)
        output = self.net.forward()
        detections: List[Detection] = []
        for result in output.reshape(-1, 7):
            confidence = float(result[2])
            if confidence < self.confidence_threshold:
                continue
            class_name = self.labels.get(int(result[1]))
            if class_name not in self.allowed_classes:
                continue
            x1 = max(0, min(width - 1, int(result[3] * width)))
            y1 = max(0, min(height - 1, int(result[4] * height)))
            x2 = max(0, min(width - 1, int(result[5] * width)))
            y2 = max(0, min(height - 1, int(result[6] * height)))
            if x2 > x1 and y2 > y1:
                detections.append(Detection(class_name, confidence, (x1, y1, x2, y2)))
        return detections
