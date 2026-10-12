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
    def run_firmware(self, source, oled, runs=((),)):
        with tempfile.TemporaryDirectory() as folder:
            declaration = f"constexpr bool OLED_TEST = {'true' if oled else 'false'};"
            sketch = (SKETCH / "ControleESP32.ino").read_text()
            sketch = sketch.replace("constexpr bool OLED_TEST = true;", declaration)
            sketch = sketch.replace("constexpr bool OLED_TEST = false;", declaration)
            (Path(folder) / "ControleESP32.ino").write_text(sketch)
            for core, usb in product((2, 3), (0, 1)):
                with self.subTest(core=core, usb=usb):
                    binary = Path(folder) / f"firmware-{core}-usb-{usb}"
                    subprocess.run([
                        "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        f"-DTEST_CORE_VERSION={core}", f"-DECO_SERIAL_USB={usb}",
                        "-I", str(TESTS / "firmware_stubs"),
                        "-I", folder, str(TESTS / source),
                        "-o", str(binary),
                    ], check=True, capture_output=True, text=True)
                    for flags in runs:
                        subprocess.run([str(binary), *flags], check=True, capture_output=True, text=True)

    def test_oled_displays_commands_and_stop_without_pwm(self):
        self.run_firmware("firmware_oled.cpp", oled=True, runs=((), ("--allocation-failed",)))

    def test_commands_ramp_watchdog_and_clock_rollover(self):
        self.run_firmware("firmware_behavior.cpp", oled=False)


if __name__ == "__main__":
    unittest.main()
