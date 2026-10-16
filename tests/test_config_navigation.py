import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import load_config


class NavigationConfigTests(unittest.TestCase):
    def load_profile(self, navigation, processing=None):
        profile = json.loads((ROOT / "config.json").read_text())
        for key in ("model_path", "config_path", "labels_path"):
            profile["ssd_mobilenet"][key] = str(ROOT / profile["ssd_mobilenet"][key])
        if navigation is None:
            profile.pop("navigation", None)
        else:
            profile["navigation"] = navigation
        if processing is not None:
            profile["image_processing"].update(processing)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text(json.dumps(profile))
            return load_config(path)

    def test_old_config_receives_tracking_defaults(self):
        config = self.load_profile(None)
        self.assertEqual(config["navigation"], {
            "horizontal_hysteresis_ratio": .03, "target_max_distance_px": 90,
            "target_min_iou": .1, "target_missing_frames": 3,
        })

    def test_rejects_invalid_tracking_parameters(self):
        for key, value in (
            ("horizontal_hysteresis_ratio", -.01), ("horizontal_hysteresis_ratio", .2),
            ("target_max_distance_px", 0), ("target_max_distance_px", float("inf")),
            ("target_min_iou", 1.1), ("target_min_iou", float("nan")),
            ("target_missing_frames", 0), ("target_missing_frames", 1.5),
            ("target_missing_frames", True),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.load_profile({key: value})

    def test_rejects_invalid_image_processing_limits(self):
        for key, value in (("max_width", 0), ("max_height", -1),
                           ("max_width", 320.5), ("max_height", True)):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.load_profile(None, {key: value})


if __name__ == "__main__":
    unittest.main()
