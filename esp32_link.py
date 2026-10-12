"""Envio serial de comandos de navegacao com confirmacao do ESP32."""
import time


class Esp32Link:
    BAUD = 115200
    READY_TIMEOUT = 8.0
    ACK_TIMEOUT = 1.0
    HEARTBEAT_INTERVAL = 1.0

    def __init__(self, port):
        try:
            import serial
        except ImportError as error:
            raise RuntimeError("Instale as dependencias do V4.1 para usar serial (pyserial)") from error
        self.connection = serial.Serial(port, self.BAUD, timeout=.1, write_timeout=.5)
        self.last_command = None
        self.last_sent_at = 0.0
        self.heartbeat_supported = False
        self.failed = False
        try:
            if self.connection.write(b"?\n") != 2:
                raise OSError("Nao foi possivel consultar o ESP32")
            self._wait_for("READY", self.READY_TIMEOUT)
            self.send("s")
        except BaseException:
            self._emergency_stop()
            self.connection.close()
            raise

    def _wait_for(self, expected, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            reply = self.connection.readline().decode("ascii", errors="replace").strip()
            if reply == "CAPS:HEARTBEAT":
                self.heartbeat_supported = True
                continue
            if reply == expected:
                return
            if reply.startswith("ERROR:"):
                raise RuntimeError(f"ESP32: {reply}")
            if reply == "TIMEOUT:s":
                raise RuntimeError("ESP32 parou por falta de comandos recentes")
            if reply in ("READY", "ARMING") and expected != "READY" and self.last_command is not None:
                raise RuntimeError("ESP32 reiniciou durante o reconhecimento")
        raise TimeoutError(f"ESP32 nao confirmou {expected!r} em {timeout:g} segundos")

    def _emergency_stop(self):
        try:
            self.connection.write(b"s\n")
        except Exception:
            pass  # O watchdog do firmware cobre a perda completa da serial.

    def send(self, command, force=False):
        if command not in ("a", "w", "d", "s"):
            raise ValueError("Comando serial deve ser a, w, d ou s")
        if self.failed and command != "s":
            raise RuntimeError("Comunicacao interrompida; reinicie o reconhecimento")
        unchanged = command == self.last_command and not force
        if unchanged and time.monotonic() - self.last_sent_at < self.HEARTBEAT_INTERVAL:
            return False
        # Renovado apenas por decisoes recentes, sem thread que mantenha movimento
        # caso a camera ou a inferencia parem de responder.
        heartbeat = unchanged and self.heartbeat_supported
        if unchanged and command == "s" and not heartbeat:
            return False
        wire_command = "h" if heartbeat else command
        expected = "HB_OK" if heartbeat else f"CMD_OK:{command}"
        message = (wire_command + "\n").encode("ascii")
        try:
            if self.connection.write(message) != len(message):
                raise OSError("Envio incompleto ao ESP32")
            self._wait_for(expected, self.ACK_TIMEOUT)
        except BaseException:
            self.failed = True
            self._emergency_stop()
            raise
        self.last_command = command
        self.last_sent_at = time.monotonic()
        return not unchanged

    def close(self):
        try:
            self.send("s", force=True)
        finally:
            self.connection.close()
