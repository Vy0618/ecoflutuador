import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from command_log import CommandLog
from detection.types import Detection
from navigation import Navigation, record_navigation


def bottle(x, y, size=20):
    return Detection("bottle", .95, (x - size // 2, y - size // 2,
                                     x + size // 2, y + size // 2))


class NavigationTests(unittest.TestCase):
    def test_four_regions_at_multiple_resolutions(self):
        for width, height in ((640, 480), (1280, 960), (321, 241)):
            for x, y, region, command in ((.15, .3, "esquerda", "a"),
                                          (.5, .3, "meio", "w"),
                                          (.85, .3, "direita", "d"),
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
        self.assertEqual(result.command, "a")

    def test_command_changes_and_missing_target(self):
        navigation = Navigation()
        self.assertTrue(navigation.update([bottle(80, 100)], 640, 480).changed)
        self.assertFalse(navigation.update([bottle(90, 100)], 640, 480).changed)
        result = navigation.update([], 640, 480)
        self.assertEqual((result.region, result.command, result.changed), (None, "s", True))
        self.assertFalse(navigation.stop().changed)

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
            self.assertEqual(terminal.getvalue(), path.read_text())
            records = [json.loads(line) for line in terminal.getvalue().splitlines()]
            self.assertEqual([item["comando"] for item in records], ["a", "a", "s"])
            self.assertEqual([item["mudou_comando"] for item in records], [True, False, True])
            self.assertEqual([item["registro"] for item in records], [1, 2, 3])
            self.assertEqual(records[-1]["evento"], "encerramento")


if __name__ == "__main__":
    unittest.main()
