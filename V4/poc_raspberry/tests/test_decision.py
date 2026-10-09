"""
Unit tests for EcoFlutuador POC decision engine and serial protocol.
"""
import sys
import os
import unittest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.decision import DecisionEngine, DecisionConfig
from core.detector import Detection
from core.serial_link import encode_command, encode_power, parse_response, SerialLink


class TestDecisionEngine(unittest.TestCase):
    """Test zone-based decision logic."""

    def setUp(self):
        self.engine = DecisionEngine(DecisionConfig(zones=3))

    def _make_detection(self, x: int, y: int = 100, w: int = 60, h: int = 100, conf: float = 0.9) -> Detection:
        return Detection(bbox=[x, y, w, h], class_name="bottle", confidence=conf)

    def test_left_zone_returns_a(self):
        """Object in left third -> 'a' (turn left)."""
        det = self._make_detection(x=50)  # center at ~80px
        result = self.engine.decide([det], frame_width=320)
        self.assertEqual(result, 'a')

    def test_center_zone_returns_w(self):
        """Object in center third -> 'w' (forward)."""
        det = self._make_detection(x=150)  # center at ~180px
        result = self.engine.decide([det], frame_width=320)
        self.assertEqual(result, 'w')

    def test_right_zone_returns_d(self):
        """Object in right third -> 'd' (turn right)."""
        det = self._make_detection(x=250)  # center at ~280px
        result = self.engine.decide([det], frame_width=320)
        self.assertEqual(result, 'd')

    def test_no_detection_returns_stop(self):
        """No objects -> 's' (stop)."""
        result = self.engine.decide([])
        self.assertEqual(result, 's')

    def test_send_only_on_change(self):
        """Repeated same decision returns None (no change)."""
        det = self._make_detection(x=50)
        result1 = self.engine.decide([det])
        result2 = self.engine.decide([det])
        self.assertEqual(result1, 'a')
        self.assertIsNone(result2)  # No change

    def test_decision_changes_when_zone_changes(self):
        """Decision updates when object moves to new zone."""
        det_left = self._make_detection(x=50)
        det_center = self._make_detection(x=150)

        r1 = self.engine.decide([det_left])
        r2 = self.engine.decide([det_center])

        self.assertEqual(r1, 'a')
        self.assertEqual(r2, 'w')

    def test_multiple_detections_picks_largest(self):
        """Should pick detection with largest area."""
        det_small = self._make_detection(x=50, w=20, h=20)    # area=400, left zone
        det_large = self._make_detection(x=250, w=80, h=80)   # area=6400, right zone
        # Large is in right zone, should win
        result = self.engine.decide([det_small, det_large], frame_width=320)
        self.assertEqual(result, 'd')

    def test_reset_clears_last_command(self):
        """Reset allows same command to be sent again."""
        det = self._make_detection(x=50)
        self.engine.decide([det])  # 'a'
        self.engine.reset()
        result = self.engine.decide([det])  # Should be 'a' again
        self.assertEqual(result, 'a')

    def test_custom_frame_width(self):
        """Zones scale with frame width."""
        engine = DecisionEngine(DecisionConfig(zones=3))
        # Left zone: 0-213px
        det = self._make_detection(x=100)  # center at 130px -> left
        result = engine.decide([det], frame_width=640)
        self.assertEqual(result, 'a')


class TestDecisionEngineResolutions(unittest.TestCase):
    """Test that decision logic works correctly at different resolutions.

    The same relative object position must produce the same decision
    regardless of the absolute resolution.
    """

    def setUp(self):
        self.engine = DecisionEngine(DecisionConfig(zones=3))

    def _make_detection_at_fraction(self, fraction_x: float, frame_width: int, frame_height: int,
                                     w: int = 60, h: int = 100, conf: float = 0.9) -> Detection:
        """Create a detection at a relative x position (0.0-1.0) in a given frame."""
        cx = int(fraction_x * frame_width)
        x = cx - w // 2
        y = (frame_height // 2) - (h // 2)
        return Detection(bbox=[x, y, w, h], class_name="bottle", confidence=conf)

    def test_left_320x240(self):
        """Object in left third at 320x240 -> 'a'."""
        det = self._make_detection_at_fraction(0.15, 320, 240)
        self.assertEqual(self.engine.decide([det], frame_width=320), 'a')

    def test_center_320x240(self):
        """Object in center third at 320x240 -> 'w'."""
        det = self._make_detection_at_fraction(0.50, 320, 240)
        self.assertEqual(self.engine.decide([det], frame_width=320), 'w')

    def test_right_320x240(self):
        """Object in right third at 320x240 -> 'd'."""
        det = self._make_detection_at_fraction(0.85, 320, 240)
        self.assertEqual(self.engine.decide([det], frame_width=320), 'd')

    def test_left_640x480(self):
        """Object in left third at 640x480 -> 'a'."""
        det = self._make_detection_at_fraction(0.15, 640, 480)
        self.assertEqual(self.engine.decide([det], frame_width=640), 'a')

    def test_center_640x480(self):
        """Object in center third at 640x480 -> 'w'."""
        det = self._make_detection_at_fraction(0.50, 640, 480)
        self.assertEqual(self.engine.decide([det], frame_width=640), 'w')

    def test_right_640x480(self):
        """Object in right third at 640x480 -> 'd'."""
        det = self._make_detection_at_fraction(0.85, 640, 480)
        self.assertEqual(self.engine.decide([det], frame_width=640), 'd')

    def test_left_1280x720(self):
        """Object in left third at 1280x720 -> 'a'."""
        det = self._make_detection_at_fraction(0.15, 1280, 720)
        self.assertEqual(self.engine.decide([det], frame_width=1280), 'a')

    def test_center_1280x720(self):
        """Object in center third at 1280x720 -> 'w'."""
        det = self._make_detection_at_fraction(0.50, 1280, 720)
        self.assertEqual(self.engine.decide([det], frame_width=1280), 'w')

    def test_right_1280x720(self):
        """Object in right third at 1280x720 -> 'd'."""
        det = self._make_detection_at_fraction(0.85, 1280, 720)
        self.assertEqual(self.engine.decide([det], frame_width=1280), 'd')

    def test_left_1920x1080(self):
        """Object in left third at 1920x1080 -> 'a'."""
        det = self._make_detection_at_fraction(0.15, 1920, 1080)
        self.assertEqual(self.engine.decide([det], frame_width=1920), 'a')

    def test_center_1920x1080(self):
        """Object in center third at 1920x1080 -> 'w'."""
        det = self._make_detection_at_fraction(0.50, 1920, 1080)
        self.assertEqual(self.engine.decide([det], frame_width=1920), 'w')

    def test_right_1920x1080(self):
        """Object in right third at 1920x1080 -> 'd'."""
        det = self._make_detection_at_fraction(0.85, 1920, 1080)
        self.assertEqual(self.engine.decide([det], frame_width=1920), 'd')

    def test_consistent_across_resolutions(self):
        """Same relative position produces same decision at all resolutions."""
        engine = DecisionEngine(DecisionConfig(zones=3))
        for fw in [320, 640, 1280, 1920]:
            det_left = self._make_detection_at_fraction(0.15, fw, fw * 3 // 4)
            det_center = self._make_detection_at_fraction(0.50, fw, fw * 3 // 4)
            det_right = self._make_detection_at_fraction(0.85, fw, fw * 3 // 4)
            self.assertEqual(engine.decide([det_left], frame_width=fw), 'a')
            self.assertEqual(engine.decide([det_center], frame_width=fw), 'w')
            self.assertEqual(engine.decide([det_right], frame_width=fw), 'd')

    def test_zone_boundaries_320(self):
        """Verify zone boundaries at 320px width."""
        zones = self.engine.get_zones(frame_width=320)
        self.assertEqual(zones["zone_width"], 106)  # 320//3 = 106
        self.assertEqual(zones["left"], (0, 106))
        self.assertEqual(zones["center"], (106, 212))  # 2*106 = 212
        self.assertEqual(zones["right"], (212, 320))

    def test_zone_boundaries_640(self):
        """Verify zone boundaries at 640px width."""
        zones = self.engine.get_zones(frame_width=640)
        self.assertEqual(zones["zone_width"], 213)  # 640//3 = 213
        self.assertEqual(zones["left"], (0, 213))
        self.assertEqual(zones["center"], (213, 426))  # 2*213 = 426
        self.assertEqual(zones["right"], (426, 640))

    def test_zone_boundaries_1280(self):
        """Verify zone boundaries at 1280px width."""
        zones = self.engine.get_zones(frame_width=1280)
        self.assertEqual(zones["zone_width"], 426)  # 1280//3 = 426
        self.assertEqual(zones["left"], (0, 426))
        self.assertEqual(zones["center"], (426, 852))  # 2*426 = 852
        self.assertEqual(zones["right"], (852, 1280))

    def test_boundary_left_edge(self):
        """Object exactly at left boundary (x=0) should be LEFT."""
        det = Detection(bbox=[0, 100, 60, 100], class_name="bottle", confidence=0.9)  # cx=30
        self.assertEqual(self.engine.decide([det], frame_width=320), 'a')

    def test_boundary_right_edge(self):
        """Object at far right should be RIGHT."""
        det = Detection(bbox=[260, 100, 60, 100], class_name="bottle", confidence=0.9)  # cx=290
        self.assertEqual(self.engine.decide([det], frame_width=320), 'd')


class TestSerialProtocol(unittest.TestCase):
    """Test serial command encoding and response parsing."""

    def test_encode_movement_commands(self):
        """All valid movement commands encode correctly."""
        for cmd in ['w', 'a', 's', 'd', 'q', 'e']:
            encoded = encode_command(cmd)
            self.assertEqual(encoded, f"{cmd}\n".encode('utf-8'))

    def test_encode_invalid_command_raises(self):
        """Invalid command raises ValueError."""
        with self.assertRaises(ValueError):
            encode_command('x')
        with self.assertRaises(ValueError):
            encode_command('W')  # uppercase not allowed

    def test_encode_power_commands(self):
        """Power commands encode correctly."""
        self.assertEqual(encode_power(1, 0), b"P1000\n")
        self.assertEqual(encode_power(1, 45), b"P1045\n")
        self.assertEqual(encode_power(1, 100), b"P1100\n")
        self.assertEqual(encode_power(2, 50), b"P2050\n")

    def test_encode_power_clamps_values(self):
        """Power values clamped to 0-100."""
        self.assertEqual(encode_power(1, -10), b"P1000\n")
        self.assertEqual(encode_power(1, 150), b"P1100\n")

    def test_encode_power_invalid_motor_raises(self):
        """Invalid motor raises ValueError."""
        with self.assertRaises(ValueError):
            encode_power(0, 50)
        with self.assertRaises(ValueError):
            encode_power(3, 50)

    def test_parse_cmd_ok(self):
        """Parse CMD_OK response."""
        result = parse_response("CMD_OK:w")
        self.assertEqual(result, {"type": "cmd_ok", "command": "w"})

        result = parse_response("CMD_OK:a")
        self.assertEqual(result, {"type": "cmd_ok", "command": "a"})

    def test_parse_pwr_ok(self):
        """Parse PWR_OK response."""
        result = parse_response("PWR_OK:1:45")
        self.assertEqual(result, {"type": "pwr_ok", "motor": 1, "value": 45})

        result = parse_response("PWR_OK:2:100")
        self.assertEqual(result, {"type": "pwr_ok", "motor": 2, "value": 100})

    def test_parse_unknown_returns_none(self):
        """Unknown response returns None."""
        self.assertIsNone(parse_response("UNKNOWN"))
        self.assertIsNone(parse_response(""))
        self.assertIsNone(parse_response("GARBAGE"))

    def test_parse_telemetry(self):
        line = ('TEL:{"schema":1,"uptime_ms":1000,'
                '"start":{"enabled":true,"detected":false},'
                '"gps":{"enabled":false,"valid":false},'
                '"water":{"ph_raw":null,"turbidity_raw":null}}')
        result = parse_response(line)
        self.assertEqual(result["type"], "telemetry")
        self.assertEqual(result["data"]["schema"], 1)
        self.assertFalse(result["data"]["start"]["detected"])

    def test_parse_invalid_telemetry_returns_none(self):
        self.assertIsNone(parse_response("TEL:{invalid}"))
        self.assertIsNone(parse_response('TEL:{"schema":2}'))
        self.assertIsNone(parse_response("TEL:[]"))

    def test_parse_start_event(self):
        self.assertEqual(
            parse_response("EVENT:START:1"),
            {"type": "start_event", "detected": True}
        )
        self.assertEqual(
            parse_response("EVENT:START:0"),
            {"type": "start_event", "detected": False}
        )
        self.assertIsNone(parse_response("EVENT:START:2"))

    def test_parse_control_responses(self):
        self.assertEqual(parse_response("BOOT:READY"), {"type": "boot", "status": "ready"})
        self.assertEqual(parse_response("PONG"), {"type": "pong"})
        self.assertEqual(
            parse_response("ERR:INVALID_COMMAND"),
            {"type": "error", "message": "INVALID_COMMAND"}
        )

    def test_parse_malformed_ack_returns_none(self):
        self.assertIsNone(parse_response("CMD_OK:x"))
        self.assertIsNone(parse_response("PWR_OK:abc"))
        self.assertIsNone(parse_response("PWR_OK:3:50"))
        self.assertIsNone(parse_response("PWR_OK:1:150"))

    def test_serial_link_valid_commands(self):
        """SerialLink.VALID_COMMANDS contains expected set."""
        self.assertEqual(SerialLink.VALID_COMMANDS, {'w', 'a', 's', 'd', 'q', 'e'})


class TestDetectionState(unittest.TestCase):
    """Test state serialization."""

    def test_empty_state(self):
        from core.state import DetectionState
        state = DetectionState.empty(timestamp=1234567890.0, fps=5.5)
        self.assertFalse(state.detected)
        self.assertEqual(state.decision, "s")
        self.assertEqual(state.fps, 5.5)
        self.assertEqual(state.timestamp, 1234567890.0)

        json_data = state.to_json()
        self.assertEqual(json_data["detected"], False)
        self.assertEqual(json_data["decision"], "s")

    def test_from_detection(self):
        from core.state import DetectionState
        state = DetectionState.from_detection(
            box=[100, 80, 60, 100],
            class_name="bottle",
            confidence=0.91,
            decision="w",
            inference_ms=180.5,
            fps=5.5,
            frame_width=320,
            frame_height=240
        )
        self.assertTrue(state.detected)
        self.assertEqual(state.object, "bottle")
        self.assertEqual(state.confidence, 0.91)
        self.assertEqual(state.center_x, round((100 + 30) / 320, 3))  # 0.406
        self.assertEqual(state.center_y, round((80 + 50) / 240, 3))   # 0.542
        self.assertEqual(state.bbox, [100, 80, 60, 100])
        self.assertEqual(state.decision, "w")
        self.assertEqual(state.inference_ms, 180.5)
        self.assertEqual(state.fps, 5.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
