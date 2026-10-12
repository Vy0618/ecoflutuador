from pathlib import Path
import sys
import time
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from camera import LatestFrameCamera


class FastCamera:
    def __init__(self):
        self.sequence = 0
        self.released = False

    def read(self):
        time.sleep(.002)
        self.sequence += 1
        return True, np.full((2, 2, 3), self.sequence, dtype=np.int32)

    def release(self):
        self.released = True


class CameraFpsTests(unittest.TestCase):
    def test_limits_consumption_even_when_device_captures_faster(self):
        device = FastCamera()
        camera = LatestFrameCamera(device, target_fps=5)
        try:
            first = camera.read()
            started = time.monotonic()
            second = camera.read()
            elapsed = time.monotonic() - started
            self.assertGreaterEqual(elapsed, .18)
            # A captura segue ativa e descarta frames intermediarios.
            self.assertGreater(int(second[0, 0, 0]), int(first[0, 0, 0]) + 5)
        finally:
            camera.close()
        self.assertTrue(device.released)

    def test_fps_setting_changes_delivery_rate(self):
        durations = []
        for fps in (5, 20):
            camera = LatestFrameCamera(FastCamera(), target_fps=fps)
            try:
                camera.read()
                started = time.monotonic()
                camera.read()
                durations.append(time.monotonic() - started)
            finally:
                camera.close()
        self.assertGreater(durations[0], durations[1] * 2)

    def test_rejects_invalid_limits(self):
        for fps in (0, -1, float("nan"), float("inf")):
            with self.subTest(fps=fps), self.assertRaises(ValueError):
                LatestFrameCamera(FastCamera(), target_fps=fps)


if __name__ == "__main__":
    unittest.main()
