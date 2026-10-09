"""V4 core. Lazy exports keep contracts/decision independent of device libraries."""
from importlib import import_module

_EXPORTS = {
    "Camera": "camera", "CameraConfig": "camera", "list_cameras": "camera",
    "Detector": "detector", "ModelConfig": "detector", "Detection": "contracts",
    "DecisionEngine": "decision", "DecisionConfig": "decision",
    "SerialLink": "serial_link", "SerialConfig": "serial_link",
    "encode_command": "serial_link", "encode_power": "serial_link", "parse_response": "serial_link",
    "DetectionState": "state",
}
__all__ = list(_EXPORTS)

def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    return getattr(import_module(f"{__name__}.{_EXPORTS[name]}"), name)
