import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import Pipeline
from core.state import RecognitionController, OperationalState, DetectionState
from core.decision import DecisionConfig, DecisionEngine
from core.detector import Detection
from core.serial_link import parse_response, SerialLink, SerialConfig
from api.status_server import StatusServer
import numpy as np


class SensorsCpp(unittest.TestCase):
    def test_firmware_sensor_logic(self):
        compiler = os.environ.get("CXX") or shutil.which("g++") or shutil.which("clang++")
        zig = os.environ.get("ZIG")
        if not compiler and not zig:
            self.skipTest("C++ compiler absent; set CXX or ZIG to run firmware logic")
        with tempfile.TemporaryDirectory() as tmp:
            exe = str(Path(tmp)/"sensors.exe")
            command = [zig, "c++", "-nostdlib++"] if zig else [compiler]
            if zig and sys.platform == 'win32':
                command = [zig, "c++", "-nostdlib", "-fno-exceptions", "-fno-rtti", "-fno-sanitize=all",
                           "-isystem", str(Path(zig).parent/'lib/libc/include/any-windows-any'),
                           "-DECO_FREESTANDING_TEST", "-Wl,--entry=mainCRTStartup", "-lkernel32"]
            subprocess.run(command+["-std=c++11", str(Path(__file__).with_name("sensors_v4_test.cpp")), "-o", exe], check=True)
            subprocess.run([exe], check=True)


class StateTests(unittest.TestCase):
    def test_start_timeout_and_rearm(self):
        c = RecognitionController(0.1, 2)
        self.assertEqual(c.state, OperationalState.WAITING)
        c.start_event(True, 0)
        self.assertEqual(c.state, OperationalState.CONFIRMING)
        c.tick(.1)
        self.assertTrue(c.active)
        c.detection(True, .2)
        self.assertEqual(c.state, OperationalState.TRACKING)
        c.tick(.4)
        self.assertTrue(c.active)
        c.tick(2.3)
        self.assertEqual(c.state, OperationalState.WAITING)
        c.start_event(True, 3)
        self.assertFalse(c.active)
        c.start_event(False, 4)
        c.start_event(True, 5)
        c.tick(5.2)
        self.assertTrue(c.active)
        c.start_event(False, 6)
        self.assertEqual(c.state, OperationalState.WAITING)

    def test_cancel_confirmation(self):
        c = RecognitionController()
        c.start_event(True, 0)
        c.start_event(False, .05)
        c.tick(1)
        self.assertFalse(c.active)


class StableDecisionTests(unittest.TestCase):
    def test_confirm_loss_hysteresis_and_metadata(self):
        e = DecisionEngine(DecisionConfig(confirmation_frames=3, loss_timeout_s=.5, hysteresis_fraction=.04))
        def det(x): return [Detection([x-10, 10, 20, 20], "bottle", .9)]
        self.assertIsNone(e.decide(det(40), now=0))
        self.assertIsNone(e.decide(det(40), now=.1))
        self.assertEqual(e.decide(det(40), now=.2), 'a')
        self.assertIsNone(e.decide([], now=.3))
        for i in range(3): self.assertIsNone(e.decide(det(110), now=.4+i*.1))
        self.assertEqual(e.details()['current_command'], 'a')
        self.assertIsNone(e.decide(det(160), now=.7))
        self.assertIsNone(e.decide(det(160), now=.8))
        self.assertEqual(e.decide(det(160), now=.9), 'w')
        self.assertEqual(e.details()['previous_command'], 'a')
        self.assertTrue(e.details()['reason'])
        self.assertGreater(e.details()['last_change_timestamp'], 0)
        self.assertEqual(e.decide([], now=1.5), 's')


class PipelineTests(unittest.TestCase):
    def pipeline(self, mode='dry-run'):
        p = Pipeline({'recognition': {'confirmation_s': 0}}, mode)
        p._decision = DecisionEngine(DecisionConfig(confirmation_frames=3, loss_timeout_s=.5))
        p._detector = Mock()
        p._detector.detect.return_value = [Detection([10,10,40,40], 'bottle', .9)]
        return p

    def test_waiting_no_inference_start_and_stop(self):
        p = self.pipeline()
        frame = np.zeros((240,320,3), np.uint8)
        self.assertEqual(p._process_frame(frame).decision, 's')
        p._detector.detect.assert_not_called()
        p._on_serial_response('EVENT:START:1')
        for _ in range(3): p._process_frame(frame)
        self.assertEqual(p.controller.state, OperationalState.TRACKING)
        self.assertEqual(p._decision.details()['current_command'], 'a')
        p._on_serial_response('EVENT:START:0')
        self.assertEqual(p._process_frame(frame).decision, 's')
        self.assertEqual(p._detector.detect.call_count, 3)

    def test_stop_during_inference(self):
        p = self.pipeline()
        def detect(frame):
            p._on_serial_response('EVENT:START:0')
            return [Detection([10,10,40,40], 'bottle', .9)]
        p._detector.detect.side_effect = detect
        p._on_serial_response('EVENT:START:1')
        self.assertEqual(p._process_frame(np.zeros((240,320,3))).decision, 's')

    def test_retains_telemetry_age_and_events(self):
        p = self.pipeline()
        tel = {'schema':1, 'ultrasonic': {'enabled':True, 'valid':True, 'start_detected':True}, 'net':{'passage_count':4}, 'water':{'ph':7}}
        p._on_serial_response('TEL:'+json.dumps(tel))
        p._service(10)
        p._on_serial_response('TEL:{bad}')
        p._on_serial_response('EVENT:NET:BLOCKED')
        p._service(11)
        self.assertEqual(p._last_telemetry, tel)
        self.assertEqual(p.runtime_status(11)['telemetry_age_ms'], 1000)
        self.assertTrue(p._net['blocked'])
        self.assertEqual(p._net['passage_count'], 4)

    def test_real_changes_only_and_offline_stop(self):
        p = self.pipeline('real')
        p._serial = Mock(connected=True)
        p._serial.send_command.return_value = True
        p._on_serial_response('TEL:{"schema":1,"start":{"detected":true}}')
        frame = np.zeros((240,320,3))
        for _ in range(5): p._process_frame(frame)
        self.assertEqual([c.args[0] for c in p._serial.send_command.call_args_list], ['s','a'])
        p._service(time.monotonic()+10)
        self.assertEqual(p.controller.state, OperationalState.FAULT)
        self.assertEqual(p._serial.send_command.call_args.args[0], 's')
        self.assertFalse(p.runtime_status(time.monotonic()+10)['serial_connected'])

    @patch('main.StatusServer')
    @patch('main.Detector')
    @patch('main.Camera')
    @patch('main.SerialLink')
    def test_dry_run_never_opens_serial(self, serial, camera, detector, api):
        p = Pipeline({'api':{'enabled':False}}, 'dry-run')
        self.assertTrue(p.setup())
        p.shutdown()
        serial.assert_not_called()

    def test_no_frame_timeout_stops(self):
        p = self.pipeline()
        p._on_serial_response('EVENT:START:1')
        p._service(10)
        p._decision._last_command = 'w'
        p._service(13)
        self.assertEqual(p.controller.state, OperationalState.WAITING)
        self.assertEqual(p._decision.details()['current_command'], 's')


class ProtocolApiTests(unittest.TestCase):
    def test_fragmented_serial_lines(self):
        chunks = iter([b'TEL:{"schema":', b'1}\nEVENT:STA', b'RT:1\n'])
        messages = []
        link = SerialLink(SerialConfig(), on_response=messages.append)
        link._ser = Mock(is_open=True, in_waiting=64)
        link._running = True
        def read(size):
            try:
                return next(chunks)
            except StopIteration:
                link._running = False
                return b''
        link._ser.read.side_effect = read
        link._read_loop()
        self.assertEqual(messages, ['TEL:{"schema":1}', 'EVENT:START:1'])

    def test_camera_buffer_consumed_once(self):
        from core.camera import Camera, CameraConfig
        camera = Camera(CameraConfig())
        camera._frame = np.zeros((2,2,3))
        self.assertIsNotNone(camera.get_frame())
        self.assertIsNone(camera.get_frame())

    def test_events_and_invalid_json(self):
        for event in ('BLOCKED','PASS','FULL_SUSPECTED','CLEAR'):
            self.assertEqual(parse_response('EVENT:NET:'+event), {'type':'net_event','event':event})
        for payload in ('{"schema":1,"x":NaN}', '{"schema":1,"x":1e999}', '{"schema":1,"ultrasonic":[]}', '{"schema":1,"net":{"blocked":"false"}}', '{"schema":1,"frame":"abc"}'):
            self.assertIsNone(parse_response('TEL:'+payload))
        self.assertIsNone(parse_response('EVENT:NET:UNKNOWN'))
        self.assertIsNone(parse_response('EVENT:START:garbage:1'))
        self.assertIsNone(parse_response('TEL:{"schema":1,"nested":'+ '['*100+'0'+']'*100+'}'))

    def test_json_only_routes(self):
        server = StatusServer()
        server.update_state(DetectionState.empty())
        server.update_telemetry({'schema':1, 'water':{'ph':7}})
        with server._app.test_client() as client:
            for route in ('/health','/status','/detections','/decision'):
                response = client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.is_json)
                text = response.get_data(as_text=True).lower()
                for word in ('base64','image','video','frame','mjpeg'):
                    self.assertNotIn(word, text)
            status = client.get('/status').json
            for field in ('operational_state','ultrasonic','net','environmental','serial_connected','telemetry_age_ms','camera_backend','recognition_active','last_error'):
                self.assertIn(field, status)
            self.assertEqual(status['environmental']['ph'], 7)
            self.assertEqual(client.get('/stream').status_code, 404)
            self.assertEqual(client.get('/video').status_code, 404)

    def test_serial_reconnect_does_not_stop_reader(self):
        link = SerialLink(SerialConfig(reconnect_delay=0))
        link._running = True
        link._ser = Mock()
        with patch.object(link, 'connect') as connect:
            link._reconnect()
            connect.assert_called_once()
            self.assertTrue(link._running)


if __name__ == '__main__':
    unittest.main()
