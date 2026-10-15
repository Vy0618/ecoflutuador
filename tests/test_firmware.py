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
    def run_firmware(self, source, oled, runs=((),), ultrasonic=None):
        with tempfile.TemporaryDirectory() as folder:
            sketch = (SKETCH / "ControleESP32.ino").read_text()
            if ultrasonic is None:
                ultrasonic = not oled
            (Path(folder) / "ControleESP32.ino").write_text(sketch)
            for core, usb in product((2, 3), (0, 1)):
                with self.subTest(core=core, usb=usb):
                    binary = Path(folder) / f"firmware-{core}-usb-{usb}"
                    subprocess.run([
                        "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        f"-DTEST_CORE_VERSION={core}", f"-DECO_SERIAL_USB={usb}",
                        f"-DTEST_ULTRASONIC={int(ultrasonic)}",
                        "-I", str(TESTS / "firmware_stubs"),
                        "-I", folder, str(TESTS / source),
                        "-o", str(binary),
                    ], check=True, capture_output=True, text=True)
                    for flags in runs:
                        subprocess.run([str(binary), *flags], check=True, capture_output=True, text=True)

    def test_oled_displays_commands_and_stop_without_pwm(self):
        self.run_firmware("firmware_oled.cpp", oled=True, runs=((), ("--allocation-failed",)), ultrasonic=True)

    def test_oled_default_works_without_sensor_and_without_thirty_second_limit(self):
        self.run_firmware("firmware_oled.cpp", oled=True)

    def test_commands_ramp_watchdog_and_clock_rollover(self):
        self.run_firmware("firmware_behavior.cpp", oled=False)

    def test_configuration_frames_mode_changes_and_invalid_requests(self):
        self.run_firmware("firmware_configuration.cpp", oled=True)


if __name__ == "__main__":
    unittest.main()
