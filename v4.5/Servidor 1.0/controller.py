"""Coordena modo, detecção e comandos; não conhece HTTP nem HTML."""
from threading import Lock
from camera import Camera
from command_log import CommandLog
from detector import Detector
from navigator import decidir_acao
from serial_manager import SerialManager, VALID_COMMANDS


class Controller:
    def __init__(self, config, serial_manager=None, camera=None, detector_factory=Detector):
        self.config = config
        self.log = CommandLog()
        self._lock = Lock()
        self._auto = False
        self._generation = 0
        self._last_command = None
        self._detector = None
        self._detector_factory = detector_factory
        self.serial = serial_manager if serial_manager is not None else SerialManager(
            config, self.log, on_disconnect=self._disconnected)
        self.camera = camera if camera is not None else Camera(config, self.log, self.process_frame)
        self.powers = {1: 30, 2: 30}

    def start(self):
        try:
            self.serial.start()
            self.camera.start()
        except Exception:
            self.stop()
            raise

    @property
    def automatic(self):
        with self._lock:
            return self._auto

    def set_mode(self, automatic):
        with self._lock:
            if automatic and self._detector is None:
                # A falha do modelo não impede usar o modo manual.
                self._detector = self._detector_factory(self.config.model_dir)
            self.serial.command("s")
            self._generation += 1
            self._auto = automatic
            self._last_command = None
            self.log.register(f"Modo alterado para: {'AUTOMÁTICO' if automatic else 'MANUAL'}")
            return self._auto

    def move(self, command):
        with self._lock:
            if self._auto:
                raise PermissionError("em modo automático")
            if command not in VALID_COMMANDS:
                raise ValueError("comando inválido")
            self.serial.command(command)
            self.log.register(f"Enviado: '{command}'")

    def power(self, motor, value):
        with self._lock:
            value = self.serial.power(motor, value)
            self.powers[motor] = value
            self.log.register(f"M{motor} → {value}%")
            return value

    def process_frame(self, frame):
        with self._lock:
            if not self._auto:
                return frame
            generation = self._generation
            detector = self._detector
        try:
            # Uma inferência por captura fornece anotação e decisão.
            annotated, objects = detector.detect(frame)
            command = decidir_acao(objects, frame.shape[1])
            with self._lock:
                if not self._auto or generation != self._generation:
                    return frame
                if command != self._last_command:
                    self.serial.command(command)
                    self._last_command = command
                    self.log.register(f"[AUTO] Enviado: '{command}'")
            return annotated
        except Exception as exc:
            with self._lock:
                if generation == self._generation:
                    self._auto = False
                    self._generation += 1
                    self._last_command = None
                    try:
                        self.serial.command("s")
                    except Exception as stop_error:
                        self.log.register(f"ERRO parada: {stop_error}")
                    self.log.register(f"[AUTO] ERRO: {exc}; modo MANUAL")
            return frame

    def _disconnected(self):
        with self._lock:
            self._auto = False
            self._generation += 1
            self._last_command = None
        self.log.register("Serial perdida: modo MANUAL; movimento não será retomado")

    def stop(self):
        with self._lock:
            self._auto = False
            self._generation += 1
            try:
                self.serial.command("s")
            except Exception as exc:
                self.log.register(f"ERRO parada no encerramento: {exc}")
        self.camera.stop()
        self.serial.stop()
