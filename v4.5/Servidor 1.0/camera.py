"""Captura e codificação MJPEG; processamento opcional recebido por função."""
import cv2
from threading import Event, Lock, Thread


class Camera:
    def __init__(self, config, log, process_frame=None):
        self.config = config
        self.log = log
        self.process_frame = process_frame
        self._capture = None
        self._jpeg = None
        self._lock = Lock()
        self._stop = Event()
        self._thread = None

    def start(self):
        if self._thread is not None:
            return
        self._capture = cv2.VideoCapture(self.config.camera_index, cv2.CAP_V4L2)
        if not self._capture.isOpened():
            self._capture.release()
            self._capture = None
            raise RuntimeError("Não foi possível abrir a câmera")
        for prop, value in ((cv2.CAP_PROP_FRAME_WIDTH, self.config.width),
                            (cv2.CAP_PROP_FRAME_HEIGHT, self.config.height),
                            (cv2.CAP_PROP_FPS, self.config.fps), (cv2.CAP_PROP_BUFFERSIZE, 1)):
            self._capture.set(prop, value)
        self._stop.clear()
        self._thread = Thread(target=self._capture_loop, daemon=True, name="camera-capture")
        self._thread.start()

    def _capture_loop(self):
        while not self._stop.is_set():
            ok, frame = self._capture.read()
            if ok:
                try:
                    if self.process_frame:
                        frame = self.process_frame(frame)
                    encoded, buffer = cv2.imencode(".jpg", frame,
                        [cv2.IMWRITE_JPEG_QUALITY, self.config.jpeg_quality])
                    if encoded:
                        with self._lock:
                            self._jpeg = buffer.tobytes()
                except Exception as exc:
                    self.log.register(f"ERRO câmera: {exc}")
            self._stop.wait(1 / self.config.fps)

    def get_frame(self):
        with self._lock:
            return self._jpeg

    def frames(self):
        while not self._stop.is_set():
            frame = self.get_frame()
            if frame:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            self._stop.wait(0.05)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        if self._capture:
            self._capture.release()
            self._capture = None
        with self._lock:
            self._jpeg = None
