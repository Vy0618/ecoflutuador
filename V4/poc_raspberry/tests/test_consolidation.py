"""Safety and observability regressions. No physical serial/camera is opened."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
import logging
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import numpy as np
from main import Pipeline
from core.camera import Camera, CameraConfig
from core.config import load_config
from core.contracts import Detection
from core.decision import DecisionEngine, DecisionConfig
from core.state import RecognitionController, OperationalState, DetectionState
from core.serial_link import SerialLink, SerialConfig, parse_response
from core.logging_config import JsonFormatter
from core.telemetry import snapshot, EventHistory
from api.status_server import StatusServer


class ConfigTests(unittest.TestCase):
    def test_paths_relative_to_yaml(self):
        config=load_config(Path(__file__).resolve().parents[1]/'config.yaml')
        self.assertTrue(Path(config['model']['weights']).is_absolute())
        self.assertTrue(Path(config['model']['weights']).exists())
        self.assertEqual(config['camera']['backend'],'V4L2')

    def test_invalid_configuration(self):
        for text in ('[]','camera: []','performance: {target_fps: 0}',
                     'recognition: {window_s: .nan}','decision: {zones: 4}',
                     'model: {input_size: [0, 320]}','serial: {heartbeat_s: 2}',
                     'decision: {confidence_threshold: 1.5}','camera: {index: -1}',
                     'decision: {target_classes: bottle}'):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'config.yaml';path.write_text(text)
                with self.assertRaises(ValueError):load_config(path)

    def test_env(self):
        with patch.dict('os.environ',{'ECO_SERIAL_PORT':'/dev/test','ECO_LOG_LEVEL':'ERROR'}):
            config=load_config(Path(__file__).resolve().parents[1]/'config.yaml')
        self.assertEqual(config['serial']['port'],'/dev/test')
        self.assertEqual(config['logging']['level'],'ERROR')


class DecisionTests(unittest.TestCase):
    def test_contract_coordinates(self):
        self.assertEqual(Detection([10,20,30,40],'plastic_bottle',.9,123).to_result(),
                         {'class':'plastic_bottle','confidence':.9,'bbox':[10,20,40,60],'center':[25,40],'frame_id':123})

    def test_fauna_overrides_larger_plastic_without_confirmation_delay(self):
        engine=DecisionEngine(DecisionConfig(confirmation_frames=3))
        engine._last_command='w'
        self.assertEqual(engine.decide([Detection([10,10,100,100],'plastic_bottle',.9),Detection([1,1,5,5],'turtle',.8)]),'s')
        self.assertEqual(engine.selected.class_name,'turtle')

    def test_configurable_priority(self):
        engine=DecisionEngine(DecisionConfig(fauna_priority=False))
        self.assertEqual(engine.decide([Detection([10,10,40,40],'plastic_bottle',.9),Detection([200,1,5,5],'fish',.8)]),'a')

    def test_unknown_and_low_confidence_ignored(self):
        for name,conf in [('unknown',.99),('plastic_bag',.1)]:
            engine=DecisionEngine(DecisionConfig())
            self.assertEqual(engine.decide([Detection([10,10,40,40],name,conf)]),'s')

    def test_duplicate_frame_cannot_confirm(self):
        engine=DecisionEngine(DecisionConfig(confirmation_frames=3))
        det=Detection([1,1,30,30],'bottle',.9,10)
        engine.decide([det]);engine.decide([det]);engine.decide([det])
        self.assertEqual(engine.details()['current_command'],'s')
        self.assertIn('Frame',engine.reason)

    def test_invalid_result_stops(self):
        engine=DecisionEngine(DecisionConfig())
        engine._last_command='w'
        self.assertEqual(engine.decide([Detection([1,2,-1,2],'bottle',.9)]),'s')

    def test_continuous_detections_still_have_window_limit(self):
        controller=RecognitionController(0,2,3)
        controller.start_event(True,0);controller.tick(0)
        for now in [1,2,2.9]:controller.detection(True,now);controller.tick(now)
        controller.tick(3)
        self.assertEqual(controller.state,OperationalState.WAITING)
        controller.start_event(True,4);controller.tick(4)
        self.assertFalse(controller.active)


class SafetyTests(unittest.TestCase):
    def pipeline(self,mode='dry-run'):
        p=Pipeline({'recognition':{'confirmation_s':0}},mode)
        p._decision=DecisionEngine(DecisionConfig(confirmation_frames=1))
        p._detector=Mock()
        p._detector.detect.return_value=[Detection([10,10,30,30],'bottle',.9)]
        return p

    def test_heartbeat_keeps_regular_commands_deduplicated(self):
        p=self.pipeline('real');p._serial=Mock(connected=True)
        p._last_sent='a';p._last_heartbeat=10;p._telemetry_time=10
        p.controller.state=OperationalState.TRACKING;p.controller.since=10;p.controller.last_detection=10
        p._service(10.6)
        p._serial.send_heartbeat.assert_called_once_with('a')
        p._serial.send_command.assert_not_called()

    def test_reconnect_forces_stop_and_fresh_start(self):
        p=self.pipeline('real');p._serial=Mock(connected=True,generation=2)
        p._last_generation=1;p._last_sent='w';p.controller.state=OperationalState.TRACKING
        p._on_serial_response('TEL:{"schema":1,"start":{"detected":true}}')
        p._service()
        self.assertFalse(p.controller.active)
        self.assertEqual(p._serial.send_command.call_args.args[0],'s')
        p._on_serial_response('EVENT:START:0');p._on_serial_response('EVENT:START:1');p._service()
        self.assertTrue(p.controller.active)

    def test_invalid_hcsr04_does_not_recover_on_same_tel(self):
        p=self.pipeline();p.controller.state=OperationalState.TRACKING;p._decision._last_command='w'
        tel='TEL:{"schema":1,"ultrasonic":{"enabled":true,"valid":false,"start_detected":true}}'
        p._on_serial_response(tel);p._service()
        self.assertEqual(p.controller.state,OperationalState.FAULT)
        self.assertEqual(p._decision.details()['current_command'],'s')
        p._on_serial_response(tel);p._service()
        self.assertEqual(p.controller.state,OperationalState.FAULT)

    def test_inference_error_stops_and_cleans_up(self):
        p=self.pipeline();p._camera=Mock();p._camera.get_frame.return_value=np.zeros((40,40,3),np.uint8)
        p._detector.detect.side_effect=RuntimeError('detector failed')
        p._on_serial_response('EVENT:START:1');p._running=True
        self.assertEqual(p.run(),1)
        self.assertEqual(p._decision.details()['current_command'],'s')
        p._camera.stop.assert_called_once()

    def test_slow_inference_cannot_send_movement(self):
        p=self.pipeline();p._on_serial_response('EVENT:START:1')
        with patch('main.time.perf_counter',side_effect=[0,2]):
            state=p._process_frame(np.zeros((40,40,3),np.uint8))
        self.assertEqual(state.decision,'s')
        self.assertEqual(p.controller.state,OperationalState.FAULT)

    @patch('main.Camera')
    @patch('main.Detector')
    @patch('main.StatusServer')
    def test_api_failure_does_not_abort_navigation(self,api,detector,camera):
        api.return_value.start.side_effect=OSError('server offline')
        p=Pipeline({},'dry-run')
        self.assertTrue(p.setup())
        self.assertIsNone(p._status_server)
        p.shutdown()

    @patch('main.Camera')
    @patch('main.SerialLink')
    def test_mock_backend_forbidden_in_production(self,serial,camera):
        p=Pipeline({'model':{'backend':'mock'}},'real')
        self.assertFalse(p.setup());serial.assert_not_called()
        camera.return_value.stop.assert_called()

    def test_stale_capture_discarded(self):
        camera=Camera(CameraConfig())
        camera._frame=np.zeros((2,2,3));camera._captured_at=time.monotonic()-2
        self.assertIsNone(camera.get_frame())

    def test_old_firmware_cannot_enable_production_control(self):
        p=self.pipeline('real');p.config['serial']={'require_control_lease':True}
        p._serial=Mock(connected=True)
        p._on_serial_response('TEL:{"schema":1,"start":{"detected":true}}')
        p._service()
        self.assertEqual(p.controller.state,OperationalState.FAULT)
        self.assertEqual(p._serial.send_command.call_args.args[0],'s')

    def test_environmental_types_rejected(self):
        for payload in ({'schema':1,'water':{'ph':'7'}}, {'schema':1,'gps':{'lat':True}}, {'schema':1,'uptime_ms':False}):
            self.assertIsNone(parse_response('TEL:'+json.dumps(payload)))

    def test_camera_gap_does_not_count_as_confirmation(self):
        p=self.pipeline()
        p._decision=DecisionEngine(DecisionConfig(confirmation_frames=3))
        p._on_serial_response('EVENT:START:1')
        image=np.zeros((240,320,3),np.uint8)
        p._process_frame(image,1);p._service();p._process_frame(image,2)
        self.assertEqual(p._decision.details()['current_command'],'s')
        p._process_frame(image,3)
        self.assertEqual(p._decision.details()['current_command'],'a')

    def test_queued_old_telemetry_cannot_refresh_connection(self):
        p=self.pipeline('real');p._serial=Mock(connected=True)
        p._responses.put((time.monotonic()-10,'TEL:{"schema":1,"start":{"detected":true}}'))
        p._service()
        self.assertIsNone(p._telemetry_time)
        self.assertEqual(p.controller.state,OperationalState.FAULT)

    def test_camera_lock_rejects_second_owner(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ',{'XDG_RUNTIME_DIR':folder}):
            first=Camera(CameraConfig());second=Camera(CameraConfig())
            try:
                with patch.object(first,'_start_opencv',return_value=True), patch.object(second,'_start_opencv',return_value=True) as start:
                    self.assertTrue(first.start());self.assertFalse(second.start());start.assert_not_called()
            finally:
                first.stop();second.stop()

    def test_heartbeat_encoding(self):
        link=SerialLink(SerialConfig())
        with patch.object(link,'_write',return_value=True) as write:
            self.assertTrue(link.send_heartbeat('w'));write.assert_called_once_with('HB:w\n')
        self.assertEqual(parse_response('HB_OK'),{'type':'heartbeat_ack'})


class ObservabilityTests(unittest.TestCase):
    def test_json_escaping(self):
        record=logging.LogRecord('test',logging.ERROR,'',0,'quoted "value"\nsecond line',(),None)
        self.assertEqual(json.loads(JsonFormatter().format(record))['message'],'quoted "value"\nsecond line')

    def test_schema_no_media_and_missing_values(self):
        payload=snapshot(DetectionState.empty().to_json(),{},None)
        self.assertIsNone(payload['sensors']['ph']);self.assertFalse(payload['gps']['fix'])
        self.assertEqual(payload['navigation']['command'],'STOP')
        self.assertIsNone(payload['vision']['confidence'])
        for field in ('jpeg','base64','image','video'):
            self.assertNotIn(field,json.dumps(payload))

    def test_history_is_bounded_and_rate_limited(self):
        history=EventHistory(capacity=3,interval_s=5)
        payload=snapshot(DetectionState.empty().to_json(),{},None)
        self.assertTrue(history.update(payload,0));self.assertFalse(history.update(payload,1))
        for t in range(5,100,5):history.update(payload,t)
        self.assertEqual(len(history.events),3)

    def test_dashboard_and_diagnostic_routes_read_only(self):
        server=StatusServer()
        with server._app.test_client() as client:
            for route in ('/','/telemetry','/history','/diagnostics'):
                self.assertEqual(client.get(route).status_code,200)
            for route in ('/move','/power','/stream','/shutdown'):
                self.assertEqual(client.get(route).status_code,404)
            self.assertEqual(client.post('/telemetry',json={}).status_code,405)

    def test_telemetry_zone_matches_decision_boundaries(self):
        state=DetectionState.from_detection([96,0,20,20],'bottle',.9,'w',0,10,320,240)
        payload=snapshot(state.to_json(),{},None)
        self.assertEqual(payload['vision']['zone'],'CENTER')
        self.assertEqual(DecisionEngine(DecisionConfig()).decide([Detection([96,0,20,20],'bottle',.9)]),'w')

    def test_stale_gps_not_reported_as_current_fix(self):
        payload=snapshot({}, {'serial_connected':False}, {'gps':{'valid':True,'lat':1,'lon':2}})
        self.assertFalse(payload['gps']['fix'])


if __name__=='__main__':unittest.main()
