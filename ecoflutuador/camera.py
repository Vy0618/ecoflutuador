"""Captura USB portátil, com apenas o frame mais recente em memória."""

from dataclasses import dataclass
import platform
import math
import time
from threading import Condition, Event, Thread

import cv2


@dataclass(frozen=True)
class WebcamConfig:
    device_index: int = 0
    width: int = 640
    height: int = 480
    fps: int = 15
    backend: int | None = None

    def open_camera(self):
        if min(self.width, self.height, self.fps) <= 0:
            raise ValueError("Resolução e FPS devem ser positivos.")
        backend = self.backend
        if backend is None:
            backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_V4L2
        camera = cv2.VideoCapture(self.device_index, backend)
        if not camera.isOpened():
            camera.release()
            raise RuntimeError(f"Não foi possível abrir a webcam {self.device_index}. Verifique conexão, permissões e camera.device_index/backend no JSON.")
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        camera.set(cv2.CAP_PROP_FPS, self.fps)
        camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return camera


class LatestFrameCamera:
    """Drena a câmera durante a inferência para não acumular vídeo atrasado."""

    def __init__(self, camera, target_fps=None):
        if target_fps is not None and (not math.isfinite(target_fps) or target_fps <= 0):
            raise ValueError("O limite de FPS deve ser positivo e finito")
        self.camera = camera
        self.frame_interval = 0 if target_fps is None else 1 / target_fps
        self.last_delivery = None
        self.condition = Condition()
        self.stopped = Event()
        self.frame = None
        self.fresh_frame = False
        self.error = None
        self.thread = Thread(target=self._capture, name="camera", daemon=True)
        self.thread.start()

    def _capture(self):
        try:
            while not self.stopped.is_set():
                success, frame = self.camera.read()
                if not success or frame is None or frame.size == 0:
                    raise RuntimeError("Não foi possível ler um frame da câmera.")
                with self.condition:
                    self.frame = frame
                    self.fresh_frame = True
                    self.condition.notify_all()
        except Exception as error:
            with self.condition:
                self.error = error
                self.condition.notify_all()

    def read(self):
        """Entrega o frame mais recente; o consumidor deve tratá-lo como somente leitura."""
        # Mantem a captura drenada; limita apenas a entrega do frame mais recente.
        if self.last_delivery is not None:
            remaining = self.last_delivery + self.frame_interval - time.monotonic()
            if remaining > 0 and self.stopped.wait(remaining):
                raise RuntimeError("Camera encerrada")
        with self.condition:
            ready = self.condition.wait_for(
                lambda: self.fresh_frame or self.error is not None or self.stopped.is_set(),
                timeout=5,
            )
            if self.stopped.is_set():
                raise RuntimeError("Camera encerrada")
            if self.error is not None:
                raise RuntimeError("Falha na captura da câmera.") from self.error
            if not ready:
                raise RuntimeError("A câmera não entregou um frame em 5 segundos.")
            self.fresh_frame = False
            self.last_delivery = time.monotonic()
            return self.frame

    def close(self):
        self.stopped.set()
        with self.condition:
            self.condition.notify_all()
        self.thread.join(timeout=1)
        self.camera.release()
        self.thread.join(timeout=1)
