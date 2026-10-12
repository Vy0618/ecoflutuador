"""
Object detector module for EcoFlutuador POC.
Wraps OpenCV DNN SSD MobileNet v3 Large (COCO).
"""
import cv2
import os
import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class ModelConfig:
    weights: str
    config: str
    classes: str
    input_size: Tuple[int, int] = (320, 320)
    conf_threshold: float = 0.45
    nms_threshold: float = 0.2
    target_classes: List[str] = None
    input_scale: float = 1.0 / 127.5
    input_mean: Tuple[float, float, float] = (127.5, 127.5, 127.5)
    class_filter: Optional[List[str]] = None

    def __post_init__(self):
        if self.target_classes is None:
            self.target_classes = ["bottle"]


from core.contracts import Detection, DetectorBackend


class Detector:
    """
    SSD MobileNet v3 Large detector via OpenCV DNN.
    Loads TensorFlow model (.pb + .pbtxt) and COCO class names.
    """

    def __init__(self, config: ModelConfig):
        self.config = config
        self._net: Optional[cv2.dnn_DetectionModel] = None
        self._class_names: List[str] = []
        self._logger = logging.getLogger(__name__)
        self._load_model()

    def _load_model(self) -> None:
        """Load model files and initialize OpenCV DNN."""
        # Check all required files exist
        missing = []
        for path, name in [(self.config.weights, "weights"),
                           (self.config.config, "config"),
                           (self.config.classes, "classes")]:
            if not os.path.exists(path):
                missing.append(f"{name}: {path}")

        if missing:
            raise FileNotFoundError(
                "Model files not found:\n  " + "\n  ".join(missing) +
                "\n\nPlease download the SSD MobileNet v3 Large COCO model and place files in models/ directory.\n"
                "Required files:\n"
                "  - frozen_inference_graph.pb (model weights)\n"
                "  - ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt (model config)\n"
                "  - coco.names (class names)\n"
                "Download from: https://github.com/opencv/opencv/wiki/TensorFlow-Object-Detection-API"
            )

        # Load class names
        with open(self.config.classes, "rt") as f:
            self._class_names = f.read().rstrip("\n").split("\n")

        # Load model
        self._net = cv2.dnn_DetectionModel(self.config.weights, self.config.config)
        self._net.setInputSize(*self.config.input_size)
        self._net.setInputScale(self.config.input_scale)
        self._net.setInputMean(self.config.input_mean)
        self._net.setInputSwapRB(True)

        self._logger.info(f"Model loaded: {len(self._class_names)} classes, input {self.config.input_size}")
        self._logger.info(f"Target classes: {self.config.target_classes}")

    def detect(self, frame) -> List[Detection]:
        """
        Run inference on frame.
        Returns recognized classes, optionally restricted by class_filter.
        """
        if self._net is None:
            raise RuntimeError("Detector not initialized")

        class_ids, confidences, boxes = self._net.detect(
            frame,
            confThreshold=self.config.conf_threshold,
            nmsThreshold=self.config.nms_threshold
        )

        detections = []
        if len(class_ids) > 0:
            for class_id, confidence, box in zip(class_ids.flatten(), confidences.flatten(), boxes):
                class_name = self._class_names[class_id - 1]  # COCO is 1-indexed
                if self.config.class_filter is not None and class_name not in self.config.class_filter:
                    continue
                # Return all classes; the decision policy chooses targets/fauna.
                x, y, w, h = map(int, box)
                detections.append(Detection(
                    bbox=[x, y, w, h], class_name=class_name,
                    confidence=float(confidence)
                ))

        return detections

    def get_class_names(self) -> List[str]:
        """Return all COCO class names."""
        return self._class_names.copy()
