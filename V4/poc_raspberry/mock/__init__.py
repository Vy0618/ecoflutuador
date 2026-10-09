"""
Mock package for EcoFlutuador POC.
Provides simulated camera and serial for testing without hardware.
"""
from mock.camera_mock import MockCamera
from mock.serial_mock import MockSerialLink

__all__ = ["MockCamera", "MockSerialLink"]