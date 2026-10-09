"""Stage the existing root sketch in Arduino's required directory; never upload."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--cli', default='arduino-cli')
parser.add_argument('--fqbn', default='esp32:esp32:esp32')
parser.add_argument('--jobs', type=int, default=2)
parser.add_argument('--enable-motors', action='store_true', help='Build operational PWM support; do not use for sensor tests')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='ecoflutuador-v4-') as temporary:
    sketch = Path(temporary)/'ControleESP32'
    sketch.mkdir()
    for name in ('ControleESP32.ino', 'sensors_v4.h'):
        shutil.copy2(root/name, sketch/name)
    subprocess.run([args.cli, 'compile', '--fqbn', args.fqbn,
                    '--jobs', str(args.jobs),
                    '--build-property', 'compiler.cpp.extra_flags=-DECO_ENABLE_MOTORS='+str(int(args.enable_motors)),
                    '--output-dir', str(root/'build'/'firmware'), str(sketch)], check=True)
