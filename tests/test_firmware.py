from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

TESTS = Path(__file__).resolve().parent
SKETCH = TESTS.parent / "firmware" / "ControleESP32"


@unittest.skipUnless(shutil.which("g++"), "g++ necessario para simular a logica do firmware")
class FirmwareTests(unittest.TestCase):
    def test_commands_ramp_watchdog_and_clock_rollover(self):
        with tempfile.TemporaryDirectory() as folder:
            for core in (2, 3):
                with self.subTest(core=core):
                    binary = Path(folder) / f"firmware-{core}"
                    subprocess.run([
                        "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        f"-DTEST_CORE_VERSION={core}", "-I", str(TESTS / "firmware_stubs"),
                        "-I", str(SKETCH), str(TESTS / "firmware_behavior.cpp"),
                        "-o", str(binary),
                    ], check=True, capture_output=True, text=True)
                    subprocess.run([str(binary)], check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
