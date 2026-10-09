"""Configuração da aplicação; nenhum dispositivo é aberto aqui."""
from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Config:
    serial_port: str = "/dev/ttyUSB0"
    baudrate: int = 115200
    serial_timeout: float = 1.0
    reconnect_delay: float = 2.0
    camera_index: int = 0
    width: int = 320
    height: int = 240
    fps: int = 10
    jpeg_quality: int = 50
    model_dir: Path = Path("/home/eco/Desktop/Object_Detection_Files")
    host: str = "0.0.0.0"
    port: int = 8080

    @classmethod
    def from_env(cls):
        return cls(
            serial_port=os.getenv("ECO_SERIAL_PORT", "/dev/ttyUSB0"),
            camera_index=int(os.getenv("ECO_CAMERA_INDEX", "0")),
            model_dir=Path(os.getenv("ECO_MODEL_DIR", "/home/eco/Desktop/Object_Detection_Files")).expanduser().resolve(),
            host=os.getenv("ECO_HOST", "0.0.0.0"),
            port=int(os.getenv("ECO_PORT", "8080")),
        )
