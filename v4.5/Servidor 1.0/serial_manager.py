"""Conexão, framing, leitura e escrita do protocolo USB da ESP32."""
import serial
from threading import Event, Lock, Thread

VALID_COMMANDS = frozenset("wasdqe")


class SerialManager:
    def __init__(self, config, log, on_disconnect=None):
        self.config = config
        self.log = log
        self.on_disconnect = on_disconnect
        self._port = None
        self._lock = Lock()
        self._stop = Event()
        self._thread = None

    def _connect(self):
        with self._lock:
            self._port = serial.Serial(self.config.serial_port, self.config.baudrate,
                                       timeout=self.config.serial_timeout,
                                       write_timeout=self.config.serial_timeout)
            try:
                if self._port.write(b"s\n") != 2:
                    raise serial.SerialException("Escrita inicial de STOP incompleta")
            except Exception:
                self._port.close()
                self._port = None
                raise
        self.log.register("Serial conectada")

    def start(self):
        if self._thread is not None:
            return
        self._connect()
        self._stop.clear()
        self._thread = Thread(target=self._read, daemon=True, name="esp32-reader")
        self._thread.start()

    def send(self, message):
        with self._lock:
            if self._port is None or not self._port.is_open:
                raise ConnectionError("ESP32 desconectada")
            data = (message + "\n").encode("utf-8")
            if self._port.write(data) != len(data):
                raise ConnectionError("Escrita serial incompleta")

    def command(self, command):
        if command not in VALID_COMMANDS:
            raise ValueError("comando inválido")
        self.send(command)

    def power(self, motor, value):
        if motor not in (1, 2):
            raise ValueError("motor inválido")
        value = max(0, min(100, int(value)))
        self.send(f"P{motor}{value:03d}")
        return value

    def _close_port(self):
        with self._lock:
            if self._port is not None:
                try:
                    self._port.close()
                except (serial.SerialException, OSError) as exc:
                    self.log.register(f"ERRO ao fechar serial: {exc}")
                finally:
                    self._port = None

    def _read(self):
        buffer = bytearray()
        discarding = False
        while not self._stop.is_set():
            try:
                if self._port is None:
                    if self._stop.wait(self.config.reconnect_delay):
                        break
                    self._connect()
                    continue
                if self._port.in_waiting:
                    chunk = self._port.read(min(self._port.in_waiting, 4096))
                    for value in chunk:
                        if value == 10:
                            if not discarding:
                                self._response(buffer.decode("utf-8", errors="replace").strip())
                            buffer.clear()
                            discarding = False
                        elif not discarding:
                            buffer.append(value)
                            if len(buffer) > 4096:
                                buffer.clear()
                                discarding = True
                else:
                    self._stop.wait(0.05)
            except (serial.SerialException, OSError) as exc:
                self.log.register(f"Serial perdida: {exc} — reconectando...")
                self._close_port()
                buffer.clear()
                discarding = False
                if self.on_disconnect:
                    self.on_disconnect()

    def _response(self, line):
        if line.startswith("CMD_OK:"):
            self.log.register(f"ESP32 confirmou: '{line.split(':', 1)[1]}'")
        elif line.startswith("PWR_OK:"):
            parts = line.split(":")
            if len(parts) == 3:
                self.log.register(f"Potência M{parts[1]} confirmada: {parts[2]}%")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        self._close_port()
