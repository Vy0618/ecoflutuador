import importlib.util
import itertools
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ecoflutuador.detection.types import Detection
from ecoflutuador.esp32_link import Esp32Link
from test_esp32_link import FakeSerial, startup_messages
spec = importlib.util.spec_from_file_location("recognition_video", ROOT / "object-ident.py")
recognition = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recognition)


class VideoDisplayTests(unittest.TestCase):
    def test_cli_selects_output_and_sensor_without_firmware_edits(self):
        for flags, output, ultrasonic in (([], "OLED", False),
                                           (["--ultrasonic"], "OLED", True),
                                           (["--output", "motors"], "MOTORES", True),
                                           (["--output", "motors", "--no-ultrasonic"], "MOTORES", False)):
            config = recognition.load_config()
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            camera = MagicMock()
            camera.read.side_effect = [frame, KeyboardInterrupt]
            detector = MagicMock()
            detector.detect.return_value = []
            device = FakeSerial(iniciar=False)
            with self.subTest(flags=flags), \
                 patch.object(sys, "argv", ["object-ident.py", "--serial-port", "test-port", "--no-display", *flags]), \
                 patch.object(recognition, "load_config", return_value=config), \
                 patch.object(recognition, "create_detector", return_value=detector), \
                 patch.object(recognition, "WebcamConfig"), \
                 patch.object(recognition, "LatestFrameCamera", return_value=camera), \
                 patch.object(recognition, "CommandLog"), \
                 patch("serial.Serial", return_value=device):
                self.assertEqual(recognition.main(), 0)
            self.assertEqual(device.messages[:4], startup_messages(output, ultrasonic))
            self.assertEqual(detector.detect.call_count, 0 if ultrasonic else 1)
            self.assertTrue(device.closed)

    def test_mode_argument_errors_happen_before_camera_or_serial(self):
        for flags in (("--output", "motors"), ("--ultrasonic",), ("--no-ultrasonic",),
                      ("--serial-port", "test-port", "--output", "invalid"),
                      ("--serial-port", "test-port", "--ultrasonic", "--no-ultrasonic"),
                      ("--duration", "nan"), ("--duration", "inf"), ("--duration", "0")):
            with self.subTest(flags=flags), patch.object(sys, "argv", ["object-ident.py", *flags]), \
                 patch.object(recognition, "create_detector") as detector, \
                 patch.object(recognition, "Esp32Link") as link, patch.object(sys, "stderr"):
                with self.assertRaises(SystemExit) as error:
                    recognition.main()
                self.assertEqual(error.exception.code, 2)
                detector.assert_not_called()
                link.assert_not_called()

    def test_static_image_supports_image_output_and_previous_output_argument(self):
        for flag in ("--image-output", "--output"):
            detector = MagicMock()
            detector.detect.return_value = [Detection("cell phone", .9, (20, 20, 120, 220))]
            with self.subTest(flag=flag), \
                 patch.object(sys, "argv", ["object-ident.py", "--image", "input.jpg", flag, "result.jpg"]), \
                 patch.object(recognition, "create_detector", return_value=detector), \
                 patch.object(recognition, "CommandLog"), \
                 patch.object(recognition.cv2, "imread", return_value=np.zeros((480, 640, 3), dtype=np.uint8)), \
                 patch.object(recognition.cv2, "imwrite", return_value=True) as write, \
                 patch.object(recognition, "Esp32Link") as link, patch("builtins.print") as output:
                self.assertEqual(recognition.main(), 0)
                self.assertEqual(write.call_args.args[0], "result.jpg")
                detector.detect.assert_called_once()
                link.assert_not_called()
                output.assert_called_once_with("Objetos detectados: 1")

    def test_configured_phone_through_detector_navigation_and_oled_serial(self):
        config = recognition.load_config()
        config["ssd_mobilenet"]["detection_types"] = ["cell phone"]
        config["detection_interval_ms"] = 1
        config["navigation"]["target_max_distance_px"] = 300
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        camera = MagicMock()
        camera.read.side_effect = [frame] * 5 + [KeyboardInterrupt]
        net = MagicMock()
        # Saida SSD realista: classe COCO 77 = cell phone; caixas em cada regiao.
        net.forward.side_effect = [
            np.array([[[[0, 77, .95, (x - 10) / 640, (y - 10) / 480,
                         (x + 10) / 640, (y + 10) / 480]]]], dtype=np.float32)
            for x, y in ((80, 100), (250, 100), (470, 100), (480, 375), (480, 385))
        ]
        device = FakeSerial(iniciar=True)  # OLED sem sensor anuncia INICIAR:1.
        clock = itertools.count(step=.1)
        with patch.object(sys, "argv", ["object-ident.py", "--no-display", "--serial-port", "test-port"]), \
             patch.object(recognition, "load_config", return_value=config), \
             patch.object(recognition.cv2.dnn, "readNetFromTensorflow", return_value=net), \
             patch.object(recognition, "WebcamConfig"), \
             patch.object(recognition, "LatestFrameCamera", return_value=camera), \
             patch.object(recognition, "CommandLog") as log, \
             patch("serial.Serial", return_value=device), \
             patch.object(recognition.time, "monotonic", side_effect=lambda: next(clock)):
            self.assertEqual(recognition.main(), 0)
        decisions = [call.kwargs for call in log.return_value.record.call_args_list
                     if call.kwargs.get("evento") == "reconhecimento"]
        self.assertEqual([item["comando"] for item in decisions], ["d", "w", "a", "a", "s"])
        self.assertEqual([item["objeto"] for item in decisions], ["cell phone"] * 5)
        self.assertEqual([item["garrafas_detectadas"] for item in decisions], [0] * 5)
        self.assertEqual(net.forward.call_count, 5)
        self.assertFalse(decisions[-2]["aproximacao_encerrada"])
        self.assertGreaterEqual(decisions[-2]["ymax"], 384)
        self.assertLess(decisions[-2]["centro"][1], 384)
        self.assertEqual([message for message in device.messages if message != b"h\n"],
                         startup_messages() + [b"d\n", b"w\n", b"a\n", b"s\n", b"s\n"])
        self.assertTrue(device.closed)

    def test_serial_standby_skips_inference_and_keeps_video_visible(self):
        for flags in (["--ultrasonic"], ["--output", "motors"]):
            with self.subTest(flags=flags):
                config = recognition.load_config()
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                camera = MagicMock()
                camera.read.side_effect = [frame, KeyboardInterrupt]
                detector = MagicMock()
                device = FakeSerial(iniciar=False)
                gui = {name: MagicMock() for name in (
                    "namedWindow", "resizeWindow", "moveWindow", "imshow", "waitKey",
                    "getWindowProperty", "destroyAllWindows")}
                gui["waitKey"].return_value = -1
                gui["getWindowProperty"].return_value = 1
                with patch.object(sys, "argv", ["object-ident.py", "--serial-port", "test-port", *flags]), \
                     patch.object(recognition, "load_config", return_value=config), \
                     patch.object(recognition, "create_detector", return_value=detector), \
                     patch.object(recognition, "WebcamConfig"), \
                     patch.object(recognition, "LatestFrameCamera", return_value=camera), \
                     patch.object(recognition, "CommandLog"), \
                     patch.object(recognition, "Esp32Link", Esp32Link), \
                     patch("serial.Serial", return_value=device), \
                     patch.dict(recognition.os.environ, {"DISPLAY": ":test"}), \
                     patch.object(recognition.cv2, "getBuildInformation", return_value="GUI: QT5"), \
                     patch.multiple(recognition.cv2, **gui):
                    self.assertEqual(recognition.main(), 0)
                detector.detect.assert_not_called()
                gui["imshow"].assert_called_once()
                shown = gui["imshow"].call_args.args[1]
                np.testing.assert_array_equal(shown[384, 320], (0, 230, 255))
                np.testing.assert_array_equal(shown[100, 213], (0, 230, 255))
                output = "MOTORES" if "--output" in flags else "OLED"
                self.assertEqual(device.messages, startup_messages(output, True) + [b"s\n"])
                self.assertTrue(device.closed)
                camera.close.assert_called_once()

    def test_brief_loss_keeps_command_and_expires_between_inferences(self):
        config = recognition.load_config()
        config["detection_interval_ms"] = 300
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        camera = MagicMock()
        detector = MagicMock()
        detector.detect.side_effect = [[Detection("bottle", .9, (20, 20, 120, 220))], [], []]
        device = FakeSerial()
        instants = iter((0.0, .3, .35, .41, .6, .69, .71))
        with patch.object(recognition.time, "monotonic", return_value=0.0) as clock:
            def read():
                try:
                    clock.return_value = next(instants)
                except StopIteration:
                    raise KeyboardInterrupt
                return frame

            camera.read.side_effect = read
            with patch.object(sys, "argv", ["object-ident.py", "--no-display", "--serial-port", "test-port"]), \
                 patch.object(recognition, "load_config", return_value=config), \
                 patch.object(recognition, "create_detector", return_value=detector), \
                 patch.object(recognition, "WebcamConfig"), \
                 patch.object(recognition, "LatestFrameCamera", return_value=camera), \
                 patch.object(recognition, "CommandLog") as log, \
                 patch("serial.Serial", return_value=device):
                self.assertEqual(recognition.main(), 0)
        self.assertEqual(detector.detect.call_count, 3)
        events = [call.kwargs for call in log.return_value.record.call_args_list
                  if call.kwargs.get("evento") in ("reconhecimento", "permanencia_encerrada")]
        self.assertEqual([event["comando"] for event in events], ["d", "d", "d", "s"])
        self.assertEqual(events[1]["estado"], "alvo_temporariamente_perdido")
        self.assertEqual(events[3]["evento"], "permanencia_encerrada")
        self.assertEqual(device.messages, startup_messages() + [b"d\n", b"s\n", b"s\n"])

    def test_activation_runs_inference_and_expiry_stops_it(self):
        config = recognition.load_config()
        config["detection_interval_ms"] = 1
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        camera = MagicMock()
        detector = MagicMock()
        detector.detect.return_value = [Detection("bottle", .9, (20, 20, 120, 220))]
        device = FakeSerial(iniciar=False)
        frames = iter((False, True, False))

        def read():
            try:
                active = next(frames)
            except StopIteration:
                raise KeyboardInterrupt
            if active != device.iniciar:
                device.iniciar = active
                device.replies.append(b"INICIAR:1\n" if active else b"INICIAR:0\n")
            return frame

        camera.read.side_effect = read
        clock = itertools.count(step=.1)
        with patch.object(sys, "argv", ["object-ident.py", "--no-display", "--serial-port", "test-port", "--ultrasonic"]), \
             patch.object(recognition, "load_config", return_value=config), \
             patch.object(recognition, "create_detector", return_value=detector), \
             patch.object(recognition, "WebcamConfig"), \
             patch.object(recognition, "LatestFrameCamera", return_value=camera), \
             patch.object(recognition, "CommandLog") as log, \
             patch.object(recognition, "Esp32Link", Esp32Link), \
             patch("serial.Serial", return_value=device), \
             patch.object(recognition.time, "monotonic", side_effect=lambda: next(clock)):
            self.assertEqual(recognition.main(), 0)
        detector.detect.assert_called_once()
        self.assertEqual(device.messages, startup_messages(ultrasonic=True) + [b"d\n", b"s\n"])
        states = [call.kwargs["iniciar"] for call in log.return_value.record.call_args_list
                  if call.kwargs.get("evento") == "ultrassonico"]
        self.assertEqual(states, [True, False])

    def test_expiry_during_inference_discards_the_stale_decision(self):
        config = recognition.load_config()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        camera = MagicMock()
        camera.read.side_effect = [frame, KeyboardInterrupt]
        detector = MagicMock()
        device = FakeSerial()

        def detect(_):
            device.iniciar = False
            device.replies.append(b"INICIAR:0\n")
            return [Detection("bottle", .9, (20, 20, 120, 220))]

        detector.detect.side_effect = detect
        with patch.object(sys, "argv", ["object-ident.py", "--no-display", "--serial-port", "test-port", "--ultrasonic"]), \
             patch.object(recognition, "load_config", return_value=config), \
             patch.object(recognition, "create_detector", return_value=detector), \
             patch.object(recognition, "WebcamConfig"), \
             patch.object(recognition, "LatestFrameCamera", return_value=camera), \
             patch.object(recognition, "CommandLog"), \
             patch.object(recognition, "Esp32Link", Esp32Link), \
             patch("serial.Serial", return_value=device):
            self.assertEqual(recognition.main(), 0)
        detector.detect.assert_called_once()
        self.assertEqual(device.messages, startup_messages(ultrasonic=True) + [b"s\n"])

    def test_expiry_and_reactivation_during_inference_reset_bottom_latch(self):
        config = recognition.load_config()
        config["detection_interval_ms"] = 1
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        camera = MagicMock()
        camera.read.side_effect = [frame] * 3 + [KeyboardInterrupt]
        detector = MagicMock()
        device = FakeSerial()
        near = Detection("bottle", .9, (290, 340, 350, 428))
        retreat = Detection("bottle", .9, (290, 330, 350, 418))
        results = iter(([near], [retreat], [retreat]))
        inference = 0

        def detect(_):
            nonlocal inference
            inference += 1
            if inference == 2:
                device.replies.extend((b"INICIAR:0\n", b"INICIAR:1\n"))
            return next(results)

        detector.detect.side_effect = detect
        clock = itertools.count(step=.1)
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
        decisions = [call.kwargs for call in log.return_value.record.call_args_list
                     if call.kwargs.get("evento") == "reconhecimento"]
        self.assertEqual([item["comando"] for item in decisions], ["s", "w"])
        self.assertTrue(decisions[0]["aproximacao_encerrada"])
        self.assertFalse(decisions[1]["aproximacao_encerrada"])
        self.assertIn(b"w\n", device.messages)
        self.assertEqual(detector.detect.call_count, 3)

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
        link_class.assert_called_once_with("test-port", output="oled", ultrasonic=None)
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
        positions = [(80, 100), (250, 100), (470, 100), (480, 375), (480, 384), (480, 360)]
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
        movement = [message for message in device.messages
                    if message not in (b"?\n", b"h\n") and not message.startswith(b"CONFIG:")]
        self.assertEqual(movement, [b"s\n", b"s\n", b"d\n", b"w\n", b"a\n", b"s\n", b"s\n"])
        decisions = [call.kwargs for call in log.return_value.record.call_args_list
                     if call.kwargs.get("evento") == "reconhecimento"]
        self.assertEqual([item["comando"] for item in decisions], ["d", "w", "a", "a", "s", "s"])
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

    def test_unconfirmed_shutdown_is_reported_as_failure_and_releases_camera(self):
        camera = MagicMock()
        camera.read.side_effect = KeyboardInterrupt
        link = MagicMock()
        link.close.side_effect = TimeoutError("sem confirmacao de parada")
        with patch.object(sys, "argv", ["object-ident.py", "--no-display", "--serial-port", "test-port"]), \
             patch.object(recognition, "create_detector"), \
             patch.object(recognition, "WebcamConfig"), \
             patch.object(recognition, "LatestFrameCamera", return_value=camera), \
             patch.object(recognition, "CommandLog") as log, \
             patch.object(recognition, "Esp32Link", return_value=link), \
             patch.object(recognition.sys, "stderr") as stderr:
            self.assertEqual(recognition.main(), 1)
        self.assertTrue(stderr.write.called)
        link.close.assert_called_once()
        camera.close.assert_called_once()
        log.return_value.close.assert_called_once()

    def test_cleanup_releases_remaining_resources_when_one_close_fails(self):
        for failure in ("record", "log", "camera"):
            camera = MagicMock()
            camera.read.side_effect = KeyboardInterrupt
            log = MagicMock()
            link = MagicMock()
            if failure == "record":
                def record(**fields):
                    if fields.get("evento") == "encerramento":
                        raise OSError("falha no registro final")
                log.record.side_effect = record
            elif failure == "log":
                log.close.side_effect = OSError("falha ao fechar log")
            else:
                camera.close.side_effect = OSError("falha ao fechar camera")
            gui = {name: MagicMock() for name in (
                "namedWindow", "resizeWindow", "moveWindow", "waitKey", "destroyAllWindows")}
            with self.subTest(failure=failure), \
                 patch.object(sys, "argv", ["object-ident.py", "--serial-port", "test-port"]), \
                 patch.object(recognition, "create_detector"), \
                 patch.object(recognition, "WebcamConfig"), \
                 patch.object(recognition, "LatestFrameCamera", return_value=camera), \
                 patch.object(recognition, "CommandLog", return_value=log), \
                 patch.object(recognition, "Esp32Link", return_value=link), \
                 patch.dict(recognition.os.environ, {"DISPLAY": ":test"}), \
                 patch.object(recognition.cv2, "getBuildInformation", return_value="GUI: QT5"), \
                 patch.multiple(recognition.cv2, **gui):
                with self.assertRaises(OSError):
                    recognition.main()
            link.close.assert_called_once()
            log.close.assert_called_once()
            camera.close.assert_called_once()
            gui["destroyAllWindows"].assert_called_once()


if __name__ == "__main__":
    unittest.main()
