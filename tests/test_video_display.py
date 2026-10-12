import importlib.util
import itertools
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from detection.types import Detection
from esp32_link import Esp32Link
from test_esp32_link import FakeSerial
spec = importlib.util.spec_from_file_location("recognition_video", ROOT / "object-ident.py")
recognition = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recognition)


class VideoDisplayTests(unittest.TestCase):
    def test_only_explicit_no_display_disables_video(self):
        for flags, expected in (([], True), (["--display"], True), (["--no-display"], False)):
            with self.subTest(flags=flags):
                config = recognition.load_config()
                # Um perfil antigo nao deve esconder o video silenciosamente.
                config["display"]["enabled"] = False
                camera = MagicMock()
                camera.read.side_effect = [np.zeros((480, 640, 3), dtype=np.uint8), KeyboardInterrupt]
                detector = MagicMock()
                detector.detect.return_value = []
                gui = {name: MagicMock() for name in (
                    "namedWindow", "resizeWindow", "moveWindow", "imshow", "waitKey",
                    "getWindowProperty", "destroyAllWindows")}
                gui["waitKey"].return_value = -1
                gui["getWindowProperty"].return_value = 1
                with patch.object(sys, "argv", ["object-ident.py", *flags]), \
                     patch.object(recognition, "load_config", return_value=config), \
                     patch.object(recognition, "create_detector", return_value=detector), \
                     patch.object(recognition, "WebcamConfig"), \
                     patch.object(recognition, "LatestFrameCamera", return_value=camera), \
                     patch.object(recognition, "CommandLog") as log, \
                     patch.dict(recognition.os.environ, {"DISPLAY": ":test"}), \
                     patch.object(recognition.cv2, "getBuildInformation", return_value="GUI: QT5"), \
                     patch.multiple(recognition.cv2, **gui):
                    self.assertEqual(recognition.main(), 0)
                    self.assertEqual(log.return_value.record.call_args_list[0].kwargs["video_habilitado"], expected)
                for function in gui.values():
                    self.assertEqual(function.called, expected)
                detector.detect.assert_called_once()
                camera.close.assert_called_once()

    def test_serial_sends_each_fresh_decision_and_closes_on_exit(self):
        config = recognition.load_config()
        config["detection_interval_ms"] = 1
        camera = MagicMock()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        camera.read.side_effect = [frame, frame, KeyboardInterrupt]
        detector = MagicMock()
        detector.detect.return_value = [Detection("bottle", .9, (20, 20, 120, 220))]
        link = MagicMock()
        clock = itertools.count(step=.1)
        with patch.object(sys, "argv", ["object-ident.py", "--no-display", "--serial-port", "test-port"]), \
             patch.object(recognition, "load_config", return_value=config), \
             patch.object(recognition, "create_detector", return_value=detector), \
             patch.object(recognition, "WebcamConfig"), \
             patch.object(recognition, "LatestFrameCamera", return_value=camera), \
             patch.object(recognition, "CommandLog") as log, \
             patch.object(recognition, "Esp32Link", return_value=link) as link_class, \
             patch.object(recognition.time, "monotonic", side_effect=lambda: next(clock)):
            self.assertEqual(recognition.main(), 0)
        link_class.assert_called_once_with("test-port")
        self.assertEqual([call.args[0] for call in link.send.call_args_list], ["d", "d"])
        link.close.assert_called_once()
        decisions = [call.kwargs for call in log.return_value.record.call_args_list
                     if call.kwargs.get("evento") == "reconhecimento"]
        self.assertEqual([item["modo"] for item in decisions], ["serial", "serial"])

    def test_complete_approach_through_real_navigation_and_serial_link(self):
        config = recognition.load_config()
        config["detection_interval_ms"] = 1
        config["navigation"]["target_max_distance_px"] = 300
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        camera = MagicMock()
        positions = [(80, 100), (250, 100), (470, 100), (480, 375), (480, 360)]
        camera.read.side_effect = [frame] * len(positions) + [KeyboardInterrupt]
        detector = MagicMock()
        detector.detect.side_effect = [
            [Detection("bottle", .9, (x - 10, y - 10, x + 10, y + 10))]
            for x, y in positions
        ]
        device = FakeSerial()
        clock = itertools.count(step=.15)
        with patch.object(sys, "argv", ["object-ident.py", "--no-display", "--serial-port", "test-port"]), \
             patch.object(recognition, "load_config", return_value=config), \
             patch.object(recognition, "create_detector", return_value=detector), \
             patch.object(recognition, "WebcamConfig"), \
             patch.object(recognition, "LatestFrameCamera", return_value=camera), \
             patch.object(recognition, "CommandLog") as log, \
             patch.object(recognition, "Esp32Link", Esp32Link), \
             patch("serial.Serial", return_value=device), \
             patch.object(recognition.time, "monotonic", side_effect=lambda: next(clock)):
            self.assertEqual(recognition.main(), 0)
        movement = [message for message in device.messages if message not in (b"?\n", b"h\n")]
        self.assertEqual(movement, [b"s\n", b"d\n", b"w\n", b"a\n", b"s\n", b"s\n"])
        decisions = [call.kwargs for call in log.return_value.record.call_args_list
                     if call.kwargs.get("evento") == "reconhecimento"]
        self.assertEqual([item["comando"] for item in decisions], ["d", "w", "a", "s", "s"])
        self.assertTrue(decisions[-1]["aproximacao_encerrada"])
        self.assertTrue(device.closed)
        camera.close.assert_called_once()

    def test_inference_failure_requests_stop_and_closes_camera_and_serial(self):
        config = recognition.load_config()
        config["detection_interval_ms"] = 1
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        camera = MagicMock()
        camera.read.side_effect = [frame, frame]
        detector = MagicMock()
        detector.detect.side_effect = [[Detection("bottle", .9, (20, 20, 120, 220))], RuntimeError("falha na inferencia")]
        link = MagicMock()
        clock = itertools.count(step=.1)
        with patch.object(sys, "argv", ["object-ident.py", "--no-display", "--serial-port", "test-port"]), \
             patch.object(recognition, "load_config", return_value=config), \
             patch.object(recognition, "create_detector", return_value=detector), \
             patch.object(recognition, "WebcamConfig"), \
             patch.object(recognition, "LatestFrameCamera", return_value=camera), \
             patch.object(recognition, "CommandLog"), \
             patch.object(recognition, "Esp32Link", return_value=link), \
             patch.object(recognition.time, "monotonic", side_effect=lambda: next(clock)), \
             patch.object(recognition.sys, "stderr"):
            self.assertEqual(recognition.main(), 1)
        link.close.assert_called_once()
        camera.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
