"""
Mock serial link for EcoFlutuador POC testing.
Simulates ESP32 responses to validate command protocol.
"""
from collections import deque
import threading
import time
import logging
from typing import Optional, Callable, List
from dataclasses import dataclass


@dataclass
class MockSerialConfig:
    response_delay: float = 0.01  # Simulated ESP32 processing time
    simulate_errors: bool = False
    error_rate: float = 0.0  # 0.0 to 1.0


class MockSerialLink:
    """
    Simulates ESP32 serial communication.
    Responds to commands with CMD_OK: and PWR_OK: messages.
    """

    VALID_COMMANDS = {'w', 'a', 's', 'd', 'q', 'e'}

    def __init__(self, config: MockSerialConfig,
                 on_response: Optional[Callable[[str], None]] = None):
        self.config = config
        self._on_response = on_response
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._logger = logging.getLogger(__name__)
        self._command_queue = deque(maxlen=256)
        self.sent_commands = deque(maxlen=256)
        self._lock = threading.Lock()
        self._last_sent: Optional[str] = None

    def connect(self) -> bool:
        """Simulate connection."""
        self._logger.info("Mock serial connected (simulated)")
        return True

    def start(self) -> bool:
        """Start response simulation thread."""
        if not self.connect():
            return False

        self._running = True
        self._thread = threading.Thread(target=self._response_loop, daemon=True)
        self._thread.start()
        return True

    def _response_loop(self) -> None:
        """Background thread: process queued commands and send responses."""
        while self._running:
            cmd = None
            with self._lock:
                if self._command_queue:
                    cmd = self._command_queue.popleft()

            if cmd:
                # Simulate processing delay
                time.sleep(self.config.response_delay)

                # Generate appropriate response
                if cmd.startswith('P'):  # Power command
                    # P1xxx or P2xxx
                    motor = cmd[1]
                    value = cmd[2:5]
                    response = f"PWR_OK:{motor}:{int(value)}"
                else:  # Movement command
                    response = f"CMD_OK:{cmd}"

                self._logger.debug(f"MOCK ESP32 <- {response}")
                if self._on_response:
                    try:
                        self._on_response(response)
                    except Exception as e:
                        self._logger.debug(f"Response callback error: {e}")
            else:
                time.sleep(0.02)

    def send_command(self, cmd: str) -> bool:
        """Queue movement command for simulated ESP32."""
        if cmd not in self.VALID_COMMANDS:
            self._logger.error(f"Invalid command: {cmd}")
            return False

        with self._lock:
            self._command_queue.append(cmd)
            self.sent_commands.append(cmd)
            self._last_sent = cmd
        self._logger.debug(f"MOCK ESP32 -> {cmd}")
        return True

    def send_power(self, motor: int, value: int) -> bool:
        """Queue power command for simulated ESP32."""
        if motor not in (1, 2):
            self._logger.error(f"Invalid motor: {motor}")
            return False
        value = max(0, min(100, value))
        cmd = f"P{motor}{value:03d}"
        with self._lock:
            self._command_queue.append(cmd)
            self.sent_commands.append(cmd)
            self._last_sent = cmd
        self._logger.debug(f"MOCK ESP32 -> {cmd}")
        return True

    def get_last_sent(self) -> Optional[str]:
        return self._last_sent

    def close(self) -> None:
        """Stop simulation."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        self._logger.info("Mock serial closed")

    def __enter__(self) -> "MockSerialLink":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()