"""Explicit bounded maintenance modes. No movement commands are available."""
import time
import json
from core.camera import Camera, CameraConfig


def run_diagnostic(mode, config, duration):
    if duration <= 0:
        raise ValueError("duration must be positive")
    deadline=time.monotonic()+duration
    if mode=="camera-test":
        settings=config.get("camera", {})
        camera=Camera(CameraConfig(backend=settings.get("backend","V4L2"), index=settings.get("index",0),
                                  width=settings.get("width",320),height=settings.get("height",240),fps=settings.get("fps",10)))
        count=0
        try:
            if not camera.start(): return 1
            while time.monotonic()<deadline:
                if camera.get_frame() is not None: count+=1
                time.sleep(.05)
            print(json.dumps({"frames_received":count,"duration_s":duration,"backend":settings.get("backend")}))
            return 0 if count else 1
        finally:
            camera.stop()
    import serial
    settings=config.get("serial",{})
    # These modes can only STOP and ask for diagnostics. No backend auto-detection.
    with serial.Serial(settings.get("port","/dev/serial0"),settings.get("baudrate",115200),timeout=.2,write_timeout=.2) as port:
        port.write(b's\nPING\nSTATUS?\n')
        buffer=bytearray()
        while time.monotonic()<deadline:
            buffer.extend(port.read(min(max(port.in_waiting,1),4096)))
            while b'\n' in buffer:
                line,_,buffer=buffer.partition(b'\n')
                print(line.decode(errors='replace').strip())
            if len(buffer)>16384: buffer.clear()
    return 0
