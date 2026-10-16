import contextlib
from datetime import datetime
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from command_log import CommandLog
from detection.types import Detection
from navigation import Navigation, record_navigation


def bottle(x, y, size=20):
    return Detection("bottle", .95, (x - size // 2, y - size // 2,
                                     x + size // 2, y + size // 2))


class NavigationTests(unittest.TestCase):
    def setUp(self):
        clock = patch("navigation.time.monotonic", return_value=0.0)
        self.clock = clock.start()
        self.addCleanup(clock.stop)

    def test_configured_cell_phone_generates_all_four_commands(self):
        for x, y, command in ((80, 100, "d"), (320, 100, "w"),
                              (560, 100, "a"), (320, 384, "s")):
            with self.subTest(command=command):
                phone = Detection("cell phone", .95, (x - 10, y - 10, x + 10, y + 10))
                result = Navigation(allowed_classes=["cell phone"]).update([phone], 640, 480)
                self.assertEqual(result.command, command)
                self.assertIs(result.selected, phone)
        result = Navigation(allowed_classes=["cell phone"]).update([bottle(80, 100)], 640, 480)
        self.assertEqual((result.command, result.selected), ("s", None))

    def test_target_association_keeps_its_class_when_other_class_is_near(self):
        navigation = Navigation(allowed_classes=["bottle", "cell phone"])
        phone = Detection("cell phone", .95, (60, 80, 100, 120))
        navigation.update([phone], 640, 480)
        larger_bottle = bottle(80, 100, 100)
        result = navigation.update([larger_bottle, phone], 640, 480)
        self.assertIs(result.selected, phone)
        result = navigation.update([larger_bottle], 640, 480)
        self.assertEqual((result.command, result.selected), ("d", None))
        self.assertEqual(result.state, "alvo_temporariamente_perdido")

    def test_four_regions_at_multiple_resolutions(self):
        for width, height in ((640, 480), (1280, 960), (321, 241)):
            for x, y, region, command in ((.15, .3, "esquerda", "d"),
                                          (.5, .3, "meio", "w"),
                                          (.85, .3, "direita", "a"),
                                          (.5, .9, "baixo", "s")):
                with self.subTest(width=width, region=region):
                    result = Navigation().update([bottle(int(width*x), int(height*y))], width, height)
                    self.assertEqual((result.region, result.command), (region, command))

    def test_bottom_overrides_horizontal_position(self):
        for x in (80, 320, 560):
            result = Navigation().update([bottle(x, 384)], 640, 480)
            self.assertEqual((result.region, result.command), ("baixo", "s"))

    def test_boundary_boxes_use_their_center(self):
        for x, region in ((212, "esquerda"), (213, "meio"), (426, "meio"), (427, "direita")):
            result = Navigation().update([bottle(x, 100, 60)], 640, 480)
            self.assertEqual(result.region, region)

    def test_largest_area_uses_xyxy_dimensions(self):
        small_right = Detection("bottle", .99, (500, 300, 520, 320))
        large_left = Detection("bottle", .8, (20, 20, 120, 220))
        result = Navigation().update([small_right, large_left], 640, 480)
        self.assertIs(result.selected, large_left)
        self.assertEqual(result.command, "d")

    def test_command_changes_and_missing_target(self):
        navigation = Navigation()
        self.assertTrue(navigation.update([bottle(80, 100)], 640, 480).changed)
        self.assertFalse(navigation.update([bottle(90, 100)], 640, 480).changed)
        result = navigation.update([], 640, 480)
        self.assertEqual((result.region, result.command, result.changed), ("esquerda", "d", False))
        self.clock.return_value = .4
        result = navigation.update([], 640, 480)
        self.assertEqual((result.region, result.command, result.changed), (None, "s", True))
        self.assertFalse(navigation.stop().changed)

    def test_bottom_uses_center_and_latches_stop_when_box_retreats(self):
        navigation = Navigation()
        near = Detection("bottle", .9, (290, 340, 350, 428))
        result = navigation.update([near], 640, 480)
        self.assertEqual(near.centroid[1], 384)
        self.assertEqual((result.region, result.command), ("baixo", "s"))
        retreat = Detection("bottle", .9, (290, 330, 350, 418))
        result = navigation.update([retreat], 640, 480)
        self.assertEqual(result.command, "s")
        self.assertTrue(result.approach_complete)
        self.assertEqual(result.state, "aproximacao_encerrada")

    def test_box_tip_can_enter_bottom_while_center_keeps_horizontal_command(self):
        for class_name in ("bottle", "cell phone"):
            for x, command in ((80, "d"), (320, "w"), (560, "a")):
                with self.subTest(class_name=class_name, command=command):
                    detection = Detection(class_name, .95, (x - 10, 260, x + 10, 440))
                    result = Navigation(allowed_classes=[class_name]).update([detection], 640, 480)
                    self.assertGreater(detection.bbox[3], 384)
                    self.assertLess(detection.centroid[1], 384)
                    self.assertEqual(result.command, command)
                    self.assertFalse(result.approach_complete)

    def test_vertical_center_boundary_respects_resolution_and_configured_line(self):
        for width, height in ((640, 480), (1280, 960), (321, 241)):
            for ratio in (.55, .8):
                line_y = int(height * ratio)
                for center_y, command in ((line_y - 1, "w"), (line_y, "s")):
                    with self.subTest(width=width, ratio=ratio, center_y=center_y):
                        result = Navigation(bottom_zone_ratio=ratio).update(
                            [bottle(width // 2, center_y)], width, height)
                        self.assertEqual(result.command, command)

    def test_larger_other_object_does_not_replace_current_target(self):
        navigation = Navigation()
        original = bottle(80, 100, 40)
        navigation.update([original], 640, 480)
        followed = bottle(85, 105, 40)
        other = bottle(550, 100, 100)
        result = navigation.update([other, followed], 640, 480)
        self.assertIs(result.selected, followed)
        self.assertEqual(result.command, "d")

    def test_initial_tie_is_independent_of_input_order(self):
        left, right = bottle(80, 100), bottle(550, 100)
        for detections in ([left, right], [right, left]):
            result = Navigation().update(detections, 640, 480)
            self.assertIs(result.selected, left)

    def test_lost_target_stops_after_hold_and_delays_switch(self):
        navigation = Navigation(target_missing_frames=3)
        original, other = bottle(80, 100), bottle(550, 100)
        navigation.update([original], 640, 480)
        for instant in (.3, .5, .699):
            self.clock.return_value = instant
            result = navigation.update([other], 640, 480)
            self.assertEqual(result.command, "d")
            self.assertIsNone(result.selected)
        self.clock.return_value = .701
        self.assertEqual(navigation.update([other], 640, 480).command, "s")
        result = navigation.update([other], 640, 480)
        self.assertIs(result.selected, other)
        self.assertEqual(result.command, "a")

    def test_brief_loss_reacquires_same_target(self):
        navigation = Navigation()
        navigation.update([bottle(80, 100)], 640, 480)
        self.assertEqual(navigation.update([], 640, 480).command, "d")
        result = navigation.update([bottle(90, 100), bottle(550, 100, 80)], 640, 480)
        self.assertEqual(result.selected.centroid[0], 90)
        self.assertEqual(result.command, "d")

    def test_completed_target_is_released_only_after_confirmed_disappearance(self):
        navigation = Navigation(target_missing_frames=2)
        navigation.update([bottle(320, 384)], 640, 480)
        navigation.update([], 640, 480)
        result = navigation.update([bottle(320, 370)], 640, 480)
        self.assertTrue(result.approach_complete)
        self.assertEqual(result.command, "s")
        navigation.update([], 640, 480)
        navigation.update([], 640, 480)
        result = navigation.update([bottle(80, 100)], 640, 480)
        self.assertFalse(result.approach_complete)
        self.assertEqual(result.command, "d")

    def test_hysteresis_at_both_horizontal_dividers(self):
        for positions, expected in (
            ([200, 215, 225, 235, 210, 200, 190], ["d", "d", "d", "w", "w", "w", "d"]),
            ([440, 420, 410, 400, 430, 440, 450], ["a", "a", "a", "w", "w", "w", "a"]),
        ):
            navigation = Navigation()
            actual = [navigation.update([bottle(x, 100)], 640, 480).command for x in positions]
            self.assertEqual(actual, expected)

    def test_brief_loss_preserves_horizontal_hysteresis(self):
        navigation = Navigation()
        navigation.update([bottle(200, 100)], 640, 480)
        navigation.update([], 640, 480)
        self.assertEqual(navigation.update([bottle(215, 100)], 640, 480).command, "d")

    def test_invalid_non_bottle_and_out_of_frame_boxes_stop(self):
        invalid = [
            Detection("can", .95, (10, 10, 30, 30)),
            Detection("bottle", .95, (30, 10, 10, 30)),
            Detection("bottle", .95, (-1, 10, 30, 30)),
            Detection("bottle", .95, (10, 10, 641, 30)),
            Detection("bottle", .95, (10, 10, 30, 481)),
            Detection("bottle", float("nan"), (10, 10, 30, 30)),
            Detection("bottle", .95, (10, 10, float("inf"), 30)),
            Detection("bottle", .95, (10, 10, 10, 30)),
        ]
        result = Navigation().update(invalid, 640, 480)
        self.assertEqual((result.command, result.selected), ("s", None))

    def test_zero_iou_threshold_does_not_match_remote_object(self):
        navigation = Navigation(target_min_iou=0)
        navigation.update([bottle(80, 100)], 640, 480)
        result = navigation.update([bottle(550, 100)], 640, 480)
        self.assertEqual((result.command, result.selected), ("d", None))
        self.clock.return_value = .4
        self.assertEqual(navigation.update([bottle(550, 100)], 640, 480).command, "s")

    def test_hold_keeps_each_command_until_deadline_despite_many_missing_frames(self):
        for x, command in ((80, "d"), (320, "w"), (560, "a")):
            with self.subTest(command=command):
                self.clock.return_value = 0
                navigation = Navigation(target_missing_frames=1)
                navigation.update([bottle(x, 100)], 640, 480)
                # A primeira perda pode chegar depois de uma inferencia demorada.
                for instant in (.8, .9, 1.0, 1.199):
                    self.clock.return_value = instant
                    result = navigation.update([], 640, 480)
                    self.assertEqual(result.command, command)
                    self.assertFalse(result.changed)
                    self.assertIsNone(result.selected)
                    self.assertEqual(navigation.loss_started_at, .8)
                self.clock.return_value = 1.201
                result = navigation.update([], 640, 480)
                self.assertEqual(result.command, "s")
                self.assertTrue(result.changed)

    def test_reacquisition_resets_hold_for_the_next_loss(self):
        navigation = Navigation()
        navigation.update([bottle(80, 100)], 640, 480)
        self.clock.return_value = .3
        self.assertEqual(navigation.update([], 640, 480).command, "d")
        self.assertEqual(navigation.loss_started_at, .3)
        self.clock.return_value = .4
        navigation.update([bottle(90, 100)], 640, 480)
        self.assertIsNone(navigation.loss_started_at)
        self.clock.return_value = .8
        self.assertEqual(navigation.update([], 640, 480).command, "d")
        self.clock.return_value = 1.1
        self.assertEqual(navigation.update([], 640, 480).command, "d")
        self.clock.return_value = 1.201
        self.assertEqual(navigation.update([], 640, 480).command, "s")

    def test_hold_never_delays_bottom_or_explicit_stop(self):
        navigation = Navigation()
        navigation.update([bottle(320, 370)], 640, 480)
        self.clock.return_value = .1
        self.assertEqual(navigation.update([bottle(320, 384)], 640, 480).command, "s")
        self.assertEqual(navigation.update([], 640, 480).command, "s")
        navigation = Navigation()
        navigation.update([bottle(80, 100)], 640, 480)
        self.assertEqual(navigation.update([], 640, 480).command, "d")
        self.assertEqual(navigation.stop().command, "s")
        self.assertEqual(navigation.update([], 640, 480).command, "s")

    def test_zero_hold_restores_immediate_stop(self):
        with patch("navigation.COMMAND_HOLD_MS", 0):
            navigation = Navigation()
            navigation.update([bottle(80, 100)], 640, 480)
            self.assertEqual(navigation.update([], 640, 480).command, "s")

    def test_autonomous_approach_updates_until_bottom(self):
        navigation = Navigation(target_max_distance_px=300)
        positions = [(80, 100), (250, 100), (470, 100), (480, 300), (480, 375), (480, 384), (480, 360)]
        commands = [navigation.update([bottle(x, y)], 640, 480).command for x, y in positions]
        self.assertEqual(commands, ["d", "w", "a", "a", "a", "s", "s"])

    def test_each_inference_is_logged_to_terminal_and_file(self):
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()) as terminal:
            path = Path(temporary) / "commands.jsonl"
            log = CommandLog(path)
            navigation = Navigation()
            detections = [bottle(80, 100)]
            for _ in range(2):
                result = navigation.update(detections, 640, 480)
                record_navigation(log, result, detections)
            record_navigation(log, navigation.stop(), [], event="encerramento")
            log.close()
            records = [json.loads(line) for line in path.read_text().splitlines()]
            expected_blocks = []
            for item in records:
                timestamp = datetime.fromisoformat(item["timestamp"]).astimezone(
                    ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d-%H-%S")
                expected_blocks.append(
                    f"timestamp: {timestamp}\nregiao: {item['regiao']}\n"
                    f"objeto: {item['objeto'] or 'nenhum'}\ngarrafas_detectadas: {item['garrafas_detectadas']}\n"
                    f"comando: {item['comando']}\n\n")
            self.assertEqual(terminal.getvalue(), "".join(expected_blocks))
            self.assertEqual([item["comando"] for item in records], ["d", "d", "s"])
            self.assertEqual([item["mudou_comando"] for item in records], [True, False, True])
            self.assertEqual([item["registro"] for item in records], [1, 2, 3])
            self.assertEqual(records[-1]["evento"], "encerramento")

    def test_camera_and_errors_are_saved_without_detection_blocks(self):
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()) as terminal:
            path = Path(temporary) / "commands.jsonl"
            log = CommandLog(path)
            log.record(evento="camera", fps_configurado=15)
            log.record(evento="erro", mensagem="Camera indisponivel", comando="s")
            log.close()
            self.assertEqual(terminal.getvalue(), "")
            records = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual([item["evento"] for item in records], ["camera", "erro"])


if __name__ == "__main__":
    unittest.main()
