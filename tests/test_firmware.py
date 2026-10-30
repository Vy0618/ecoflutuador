from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from itertools import product

TESTS = Path(__file__).resolve().parent
SKETCH = TESTS.parent / "firmware" / "ControleESP32"


@unittest.skipUnless(shutil.which("g++"), "g++ necessario para simular a logica do firmware")
class FirmwareTests(unittest.TestCase):
    def run_firmware(self, source, runs=((),), ultrasonic=False):
        with tempfile.TemporaryDirectory() as folder:
            for core, usb in product((2, 3), (0, 1)):
                with self.subTest(core=core, usb=usb):
                    binary = Path(folder) / f"firmware-{core}-usb-{usb}"
                    subprocess.run([
                        "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        f"-DTEST_CORE_VERSION={core}", f"-DECO_SERIAL_USB={usb}",
                        f"-DTEST_ULTRASONIC={int(ultrasonic)}",
                        "-I", str(TESTS / "firmware_stubs"),
                        "-I", str(SKETCH), str(TESTS / source),
                        "-o", str(binary),
                    ], check=True, capture_output=True, text=True)
                    for flags in runs:
                        subprocess.run([str(binary), *flags], check=True, capture_output=True, text=True)

    def test_oled_displays_commands_and_stop_without_pwm(self):
        self.run_firmware("firmware_oled.cpp", runs=((), ("--allocation-failed",)), ultrasonic=True)

    def test_oled_default_works_without_sensor_and_without_thirty_second_limit(self):
        self.run_firmware("firmware_oled.cpp")

    def test_commands_ramp_watchdog_and_clock_rollover(self):
        self.run_firmware("firmware_behavior.cpp")

    def test_configuration_frames_mode_changes_and_invalid_requests(self):
        self.run_firmware("firmware_configuration.cpp", runs=((), ("--display-failed",)))

    def test_three_sensors_share_trigger_and_capture_overlapping_echoes(self):
        self.run_firmware("firmware_ultrasonic.cpp")


if __name__ == "__main__":
    unittest.main()
