from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from detection.ssd_mobilenet_detector import SsdMobileNetDetector
from image_processing import prepare_frame, restore_coordinates


class DetectorTests(unittest.TestCase):
    def detector(self, classes):
        models = ROOT / "models"
        return SsdMobileNetDetector(
            models / "frozen_inference_graph.pb",
            models / "ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt",
            models / "coco.names", .45, 320, 320, classes,
        )

    @patch("cv2.dnn.readNetFromTensorflow")
    def test_unknown_classes_fail_before_loading_network(self, read_network):
        with self.assertRaisesRegex(ValueError, "bottles"):
            self.detector(["bottle", "bottles"])
        read_network.assert_not_called()

    @patch("cv2.dnn.readNetFromTensorflow")
    def test_filters_ssd_output_and_restores_bottle_and_phone_coordinates(self, read_network):
        rows = [
            [0, 44, .9, .125, .25, .375, .75],
            [0, 77, .8, .5, .125, .75, .625],
            [0, 44, .95, -.25, -.25, 1.25, 1.25],
            [0, 1, .9, .125, .25, .375, .75],
            [0, 44, .2, .125, .25, .375, .75],
            [0, 44, .9, .75, .25, .375, .75],
        ]
        for field in (1, 2, 3, 6):
            for value in (float("nan"), float("inf")):
                row = rows[0].copy()
                row[field] = value
                rows.append(row)
        read_network.return_value.forward.return_value = np.array(rows, dtype=np.float32)
        detector = self.detector(["bottle", "cell phone"])
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        processed = prepare_frame(frame, {"enabled": True, "max_width": 320, "max_height": 240})
        detections = restore_coordinates(detector.detect(processed), processed.shape, frame.shape)
        self.assertEqual([(item.class_name, item.bbox) for item in detections], [
            ("bottle", (80, 120, 240, 360)),
            ("cell phone", (320, 60, 480, 300)),
            ("bottle", (0, 0, 638, 478)),
        ])


if __name__ == "__main__":
    unittest.main()
