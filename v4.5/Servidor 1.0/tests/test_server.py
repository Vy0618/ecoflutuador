"""Regressões da divisão modular, sem webcam, modelo ou ESP32."""
import importlib
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from config import Config
from controller import Controller
from navigator import decidir_acao
from serial_manager import SerialManager
from web import create_app


class ModularServerTests(unittest.TestCase):
    def setUp(self):
        self.serial = Mock()
        self.serial.power.side_effect = lambda motor, value: max(0, min(100, value))
        self.camera = Mock()
        self.detector = Mock()
        self.detector.detect.side_effect = lambda frame: (frame, [[[130, 10, 30, 50], "bottle"]])
        self.factory = Mock(return_value=self.detector)
        self.controller = Controller(Config(), self.serial, self.camera, self.factory)
        self.client = create_app(self.controller).test_client()

    def test_import_entrypoint_does_not_open_hardware_or_load_model(self):
        with patch('cv2.VideoCapture') as capture, patch('serial.Serial') as serial:
            with patch('cv2.dnn_DetectionModel') as model:
                importlib.import_module('servidor')
                capture.assert_not_called()
                serial.assert_not_called()
                model.assert_not_called()

    def test_html_and_existing_assets_are_served_without_source_exposure(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'/static/script.js', response.data)
        self.assertIn(b'btn-frente', response.data)
        for name in ('style.css', 'script.js'):
            with self.client.get('/static/' + name) as asset:
                self.assertEqual(asset.status_code, 200)
        self.assertEqual(self.client.get('/static/servidor.py').status_code, 404)

    def test_manual_movement_and_validation(self):
        for command in 'wasdqe':
            response = self.client.get('/move', query_string={'cmd': command})
            self.assertEqual(response.json, {'status': 'enviado', 'cmd': command})
            self.serial.command.assert_called_with(command)
        count = self.serial.command.call_count
        self.assertEqual(self.client.get('/move?cmd=x').status_code, 400)
        self.assertEqual(self.serial.command.call_count, count)

    def test_serial_failure_is_reported(self):
        self.serial.command.side_effect = ConnectionError('offline')
        self.assertEqual(self.client.get('/move?cmd=w').status_code, 500)
        self.assertIn('offline', self.client.get('/log').json['log'][-1])

    def test_power_format_and_limits(self):
        port = Mock(is_open=True)
        port.write.side_effect = lambda message: len(message)
        manager = SerialManager(Config(), Mock())
        manager._port = port
        self.assertEqual(manager.power(1, 145), 100)
        port.write.assert_called_with(b'P1100\n')
        self.assertEqual(manager.power(2, -5), 0)
        port.write.assert_called_with(b'P2000\n')
        manager.command('w')
        port.write.assert_called_with(b'w\n')
        with self.assertRaises(ValueError):
            manager.power(3, 30)

    def test_connection_and_reconnection_always_send_stop(self):
        port = Mock()
        port.write.return_value = 2
        manager = SerialManager(Config(), Mock())
        with patch('serial_manager.serial.Serial', return_value=port):
            manager._connect()
            manager._close_port()
            manager._connect()
        self.assertEqual(port.write.call_args_list, [unittest.mock.call(b's\n')] * 2)
        manager.stop()

    def test_power_route_and_invalid_number(self):
        response = self.client.get('/power?motor=1&val=45')
        self.assertEqual(response.json, {'status': 'ok', 'motor': 1, 'potencia': 45})
        self.assertEqual(self.controller.powers[1], 45)
        self.assertEqual(self.client.get('/power?motor=x').status_code, 400)

    def test_manual_mode_does_not_load_or_run_detector(self):
        self.controller.start()
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        self.assertIs(self.controller.process_frame(frame), frame)
        self.factory.assert_not_called()
        self.detector.detect.assert_not_called()
        self.controller.stop()

    def test_automatic_uses_one_inference_per_frame_and_suppresses_repeated_command(self):
        self.assertEqual(self.client.get('/set_modo?auto=1').json, {'modo_auto': True})
        self.serial.command.reset_mock()
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        for _ in range(2):
            self.controller.process_frame(frame)
        self.assertEqual(self.detector.detect.call_count, 2)
        self.serial.command.assert_called_once_with('w')
        self.assertEqual(self.client.get('/move?cmd=a').status_code, 403)
        self.assertTrue(self.client.get('/log').json['modo_auto'])

    def test_absent_target_stops_even_on_first_automatic_frame(self):
        self.detector.detect.side_effect = lambda frame: (frame, [])
        self.controller.set_mode(True)
        self.serial.command.reset_mock()
        self.controller.process_frame(np.zeros((240, 320, 3)))
        self.serial.command.assert_called_once_with('s')

    def test_model_failure_preserves_manual_mode(self):
        self.factory.side_effect = FileNotFoundError('modelo ausente')
        self.assertEqual(self.client.get('/set_modo?auto=1').status_code, 500)
        self.assertFalse(self.controller.automatic)
        self.assertEqual(self.client.get('/move?cmd=w').status_code, 200)

    def test_detector_failure_disables_auto_and_stops(self):
        self.controller.set_mode(True)
        self.detector.detect.side_effect = RuntimeError('inferência falhou')
        self.controller.process_frame(np.zeros((240, 320, 3)))
        self.assertFalse(self.controller.automatic)
        self.serial.command.assert_called_with('s')

    def test_mode_change_during_inference_discards_old_command(self):
        started, release = threading.Event(), threading.Event()
        def detect(frame):
            started.set()
            if not release.wait(2):
                raise TimeoutError('teste')
            return frame, [[[130, 10, 30, 50], 'bottle']]
        self.detector.detect.side_effect = detect
        self.controller.set_mode(True)
        worker = threading.Thread(target=self.controller.process_frame,
                                  args=(np.zeros((240, 320, 3)),))
        worker.start()
        try:
            self.assertTrue(started.wait(1))
            self.controller.set_mode(False)
            self.serial.command.reset_mock()
        finally:
            release.set()
            worker.join(2)
        self.assertFalse(worker.is_alive())
        self.serial.command.assert_not_called()

    def test_camera_start_failure_closes_started_serial(self):
        self.camera.start.side_effect = RuntimeError('sem câmera')
        with self.assertRaises(RuntimeError):
            self.controller.start()
        self.serial.command.assert_called_with('s')
        self.serial.stop.assert_called_once()
        self.camera.stop.assert_called_once()

    def test_disconnect_disarms_auto_and_shutdown_stops(self):
        self.controller.set_mode(True)
        self.controller._disconnected()
        self.assertFalse(self.controller.automatic)
        self.controller.stop()
        self.serial.command.assert_called_with('s')
        self.camera.stop.assert_called_once()
        self.serial.stop.assert_called_once()

    def test_mjpeg_boundary(self):
        self.camera.frames.return_value = iter([
            b'--frame\r\nContent-Type: image/jpeg\r\n\r\nJPEG\r\n'])
        response = self.client.get('/stream')
        self.assertIn('boundary=frame', response.content_type)
        self.assertIn(b'JPEG', response.data)

    def test_largest_target_and_proportional_zones(self):
        self.assertEqual(decidir_acao([]), 's')
        for x, expected in ((10, 'a'), (300, 'w'), (550, 'd')):
            self.assertEqual(decidir_acao([[[x, 0, 40, 50], 'bottle']], 640), expected)
        self.assertEqual(decidir_acao([
            [[10, 0, 10, 10], 'bottle'], [[250, 0, 30, 50], 'bottle']]), 'd')


if __name__ == '__main__':
    unittest.main()
