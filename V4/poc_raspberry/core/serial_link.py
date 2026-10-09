"""
Serial communication module for EcoFlutuador POC.
Handles RPi <-> ESP32 communication protocol.
"""
import serial
import threading
import time
import logging
import json
from typing import Optional, Callable, List
from dataclasses import dataclass


@dataclass
class SerialConfig:
    port: str = "/dev/serial0"
    baudrate: int = 115200
    timeout: float = 1.0
    reconnect_delay: float = 2.0
    auto_detect: bool = True


# Common serial ports to try on Linux
COMMON_PORTS = [
    "/dev/serial0",  # stable alias for the Raspberry Pi GPIO UART
    "/dev/ttyUSB0",
    "/dev/ttyUSB1",
    "/dev/ttyACM0",
    "/dev/ttyACM1",
    "/dev/ttyAMA0",  # RPi built-in UART
]


class SerialLink:
    """
    Manages serial communication with ESP32.
    Protocol:
      RPi -> ESP32:  'w\\n', 'a\\n', 's\\n', 'd\\n', 'q\\n', 'e\\n', 'P1xxx\\n', 'P2xxx\\n'
      ESP32 -> RPi:  'CMD_OK:w\\n', 'PWR_OK:1:45\\n'
    """

    VALID_COMMANDS = {'w', 'a', 's', 'd', 'q', 'e'}

    def __init__(self, config: SerialConfig, on_response: Optional[Callable[[str], None]] = None):
        self.config = config
        self._on_response = on_response
        self._ser: Optional[serial.Serial] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._logger = logging.getLogger(__name__)
        self._last_sent: Optional[str] = None
        self.generation = 0

    def connect(self) -> bool:
        """Open serial port with auto-detect fallback."""
        ports_to_try = [self.config.port] if not self.config.auto_detect else \
                       [self.config.port] + [p for p in COMMON_PORTS if p != self.config.port]

        for port in ports_to_try:
            try:
                self._ser = serial.Serial(
                    port=port,
                    baudrate=self.config.baudrate,
                    write_timeout=self.config.timeout,
                    timeout=self.config.timeout
                )
                self.generation += 1
                self._logger.info(f"Serial connected: {port} @ {self.config.baudrate}")
                return True
            except (serial.SerialException, OSError) as e:
                self._logger.debug(f"Failed to open {port}: {e}")
                continue

        self._logger.error(f"Could not open any serial port. Tried: {ports_to_try}")
        return False

    def start(self) -> bool:
        """Connect and start reader thread."""
        if not self.connect():
            return False

        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        return True

    def _read_loop(self) -> None:
        """Background thread: read responses from ESP32."""
        buffer = bytearray()
        discarding = False
        while self._running:
            if not self.connected:
                self._reconnect()
                buffer.clear()
                discarding = False
                continue
            try:
                if self._ser.in_waiting > 0:
                    chunk = self._ser.read(min(self._ser.in_waiting, 4096))
                    if discarding:
                        if b'\n' not in chunk:
                            continue
                        chunk = chunk.split(b'\n', 1)[1]
                        discarding = False
                    buffer.extend(chunk)
                    while b'\n' in buffer:
                        raw, _, rest = buffer.partition(b'\n')
                        buffer = bytearray(rest)
                        if len(raw) <= 16384:
                            self._handle_response(raw.decode('utf-8', errors='replace').strip())
                    if len(buffer) > 16384:
                        buffer.clear()
                        discarding = True
                else:
                    time.sleep(0.01)
            except (serial.SerialException, OSError) as e:
                self._logger.warning(f"Serial read error: {e}")
                buffer.clear()
                discarding = False
                self._reconnect()
            except Exception as e:
                self._logger.debug(f"Serial read exception: {e}")
                time.sleep(0.01)

    def _handle_response(self, line: str) -> None:
        """Process response from ESP32."""
        self._logger.debug(f"ESP32 <- {line}")
        if self._on_response:
            try:
                self._on_response(line)
            except Exception as e:
                self._logger.debug(f"Response callback error: {e}")

    def _reconnect(self) -> None:
        """Attempt to reconnect serial port."""
        self._logger.info("Attempting serial reconnect...")
        with self._lock:
            if self._ser is not None:
                try:
                    self._ser.close()
                except (serial.SerialException, OSError):
                    pass
                self._ser = None
        deadline = time.monotonic()+self.config.reconnect_delay
        while self._running and time.monotonic() < deadline:
            time.sleep(0.05)
        if self._running:
            self.connect()

    def send_command(self, cmd: str) -> bool:
        """
        Send movement command to ESP32.
        Valid commands: 'w', 'a', 's', 'd', 'q', 'e'
        """
        if cmd not in self.VALID_COMMANDS:
            self._logger.error(f"Invalid command: {cmd}")
            return False

        return self._write(f"{cmd}\n")

    def send_heartbeat(self, command):
        if command not in self.VALID_COMMANDS:
            return False
        return self._write(f"HB:{command}\n")

    def send_power(self, motor: int, value: int) -> bool:
        """
        Send power command to ESP32.
        motor: 1 or 2
        value: 0-100
        Format: P1xxx\\n or P2xxx\\n (xxx = 3 digits, zero-padded)
        """
        if motor not in (1, 2):
            self._logger.error(f"Invalid motor: {motor}")
            return False
        value = max(0, min(100, value))
        return self._write(f"P{motor}{value:03d}\n")

    def _write(self, data: str) -> bool:
        """Thread-safe write to serial port."""
        with self._lock:
            if self._ser is None or not self._ser.is_open:
                self._logger.warning("Serial not connected")
                return False
            try:
                self._ser.write(data.encode('utf-8'))
                self._ser.flush()
                self._last_sent = data.strip()
                self._logger.debug(f"ESP32 -> {data.strip()}")
                return True
            except (serial.SerialException, OSError) as e:
                self._logger.error(f"Serial write error: {e}")
                return False

    @property
    def connected(self):
        return self._ser is not None and self._ser.is_open

    def get_last_sent(self) -> Optional[str]:
        """Get last command sent."""
        return self._last_sent

    def close(self) -> None:
        """Close serial port and stop reader thread."""
        self._running = False
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2.0)
            self._thread = None
        with self._lock:
            if self._ser is not None:
                try:
                    self._ser.close()
                except Exception:
                    pass
                self._ser = None
        self._logger.info("Serial closed")

    def __enter__(self) -> "SerialLink":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def encode_command(cmd: str) -> bytes:
    """Encode movement command for serial transmission."""
    if cmd not in SerialLink.VALID_COMMANDS:
        raise ValueError(f"Invalid command: {cmd}")
    return f"{cmd}\n".encode('utf-8')


def encode_power(motor: int, value: int) -> bytes:
    """Encode power command for serial transmission."""
    if motor not in (1, 2):
        raise ValueError(f"Invalid motor: {motor}")
    value = max(0, min(100, value))
    return f"P{motor}{value:03d}\n".encode('utf-8')


def parse_response(line: str) -> Optional[dict]:
    """
    Parse ESP32 response line.
    Returns dict with keys: type, command/motor, value
    """
    if not isinstance(line, str) or len(line) > 16384:
        return None
    line = line.strip()
    if line.startswith("CMD_OK:"):
        parts = line.split(":", 1)
        if len(parts) == 2 and parts[1] in SerialLink.VALID_COMMANDS:
            return {"type": "cmd_ok", "command": parts[1]}
        return None
    elif line.startswith("PWR_OK:"):
        parts = line.split(":")
        if len(parts) != 3:
            return None
        try:
            motor = int(parts[1])
            value = int(parts[2])
        except ValueError:
            return None
        if motor not in (1, 2) or not 0 <= value <= 100:
            return None
        return {"type": "pwr_ok", "motor": motor, "value": value}
    elif line.startswith("TEL:"):
        try:
            payload = json.loads(line[4:], parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
        except (ValueError, TypeError, RecursionError):
            return None
        if not isinstance(payload, dict) or type(payload.get("schema")) is not int or payload.get("schema") != 1:
            return None
        if not valid_telemetry(payload):
            return None
        return {"type": "telemetry", "data": payload}
    elif line.startswith("EVENT:START:"):
        value = line[len("EVENT:START:"):]
        if value in ("0", "1"):
            return {"type": "start_event", "detected": value == "1"}
        return None
    elif line.startswith("EVENT:NET:"):
        event = line[len("EVENT:NET:"):]
        if event in {"BLOCKED", "PASS", "FULL_SUSPECTED", "CLEAR"}:
            return {"type": "net_event", "event": event}
        return None
    elif line == "BOOT:READY":
        return {"type": "boot", "status": "ready"}
    elif line == "HB_OK":
        return {"type": "heartbeat_ack"}
    elif line == "PONG":
        return {"type": "pong"}
    elif line.startswith("ERR:"):
        return {"type": "error", "message": line[4:]}
    return None


def valid_telemetry(payload):
    """Reject malformed sections and media; retain additive schema-1 fields."""
    import math
    forbidden = {"frame", "image", "imagem", "video", "base64", "jpeg", "mjpeg"}
    def safe(value):
        pending = [(value, 0)]
        while pending:
            item, depth = pending.pop()
            if depth > 64:
                return False
            if isinstance(item, dict):
                if any(any(word in str(k).lower() for word in forbidden) for k in item):
                    return False
                pending.extend((v, depth+1) for v in item.values())
            elif isinstance(item, list):
                pending.extend((v, depth+1) for v in item)
            elif isinstance(item, float) and not math.isfinite(item):
                return False
        return True
    if not safe(payload):
        return False
    for key in ("start", "ultrasonic", "net", "gps", "water", "motors"):
        if key in payload and not isinstance(payload[key], dict):
            return False
    for key in ("uptime_ms", "control_timeout_ms"):
        if key in payload and (type(payload[key]) is not int or payload[key] < 0):
            return False
    for field, value in payload.get("water", {}).items():
        if field.endswith("_enabled"):
            if type(value) is not bool: return False
        elif field in {"ph", "ph_raw", "ph_voltage_v", "turbidity_raw", "turbidity_voltage_v", "turbidity_ntu", "temperature_c"}:
            if value is not None and type(value) not in (int,float): return False
    for field in ("lat", "lon", "altitude_m", "speed_kmh", "satellites"):
        value=payload.get("gps",{}).get(field)
        if value is not None and type(value) not in (int,float): return False
    for key in ("start", "ultrasonic", "net", "gps"):
        for field, value in payload.get(key, {}).items():
            if field in {"enabled", "valid", "detected", "calibrated", "start_detected", "blocked", "full_suspected"} and type(value) is not bool:
                return False
            if field in {"distance_cm", "baseline_cm", "delta_cm", "blocked_ms", "passage_count"} and value is not None and type(value) not in (int, float):
                return False
    return True
