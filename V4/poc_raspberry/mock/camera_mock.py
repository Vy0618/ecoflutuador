"""
Mock camera for EcoFlutuador POC testing.
Generates synthetic frames with a moving "bottle" for testing decision logic.
"""
import cv2
import numpy as np
import time
import threading
import logging
from typing import Optional, Any, Tuple
from dataclasses import dataclass


@dataclass
class MockCameraConfig:
    width: int = 320
    height: int = 240
    fps: int = 10
    bottle_speed: float = 0.5  # zones per second
    bottle_size: Tuple[int, int] = (60, 100)  # w, h
    noise_level: float = 0.05


class MockCamera:
    """
    Simulates a camera with a moving bottle.
    Bottle moves left->center->right->center->left in a sinusoidal pattern.
    Generates frames compatible with the detector input format.
    """

    def __init__(self, config: MockCameraConfig):
        self.config = config
        self._frame: Optional[Any] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._logger = logging.getLogger(__name__)
        self._start_time = time.time()
        self._zone_positions = [0.15, 0.5, 0.85]  # left, center, right as fraction of width

    def start(self) -> bool:
        """Start frame generation thread."""
        if self._running:
            return True

        self._running = True
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._generate_loop, daemon=True)
        self._thread.start()
        self._logger.info(f"Mock camera started: {self.config.width}x{self.config.height} @ {self.config.fps} FPS")
        return True

    def _generate_loop(self) -> None:
        """Background thread: generate synthetic frames."""
        frame_interval = 1.0 / self.config.fps

        while self._running:
            loop_start = time.time()

            # Calculate bottle position (sinusoidal: left <-> center <-> right)
            elapsed = time.time() - self._start_time
            # Cycle through zones: 0=left, 1=center, 2=right, 1=center, 0=left...
            cycle = (elapsed * self.config.bottle_speed) % 4
            fraction = cycle / 2 if cycle <= 2 else (4-cycle)/2
            cx = int((.15 + .7*fraction) * self.config.width)
            cy = self.config.height // 2
            bw, bh = self.config.bottle_size
            x = cx - bw // 2
            y = cy - bh // 2

            # Create frame: dark background with green "bottle" rectangle
            frame = np.zeros((self.config.height, self.config.width, 3), dtype=np.uint8)
            # Add some noise
            if self.config.noise_level > 0:
                noise = np.random.randint(0, int(255 * self.config.noise_level),
                                          (self.config.height, self.config.width, 3), dtype=np.uint8)
                frame = cv2.add(frame, noise)

            # Draw bottle (green rectangle)
            cv2.rectangle(frame, (x, y), (x + bw, y + bh), (0, 200, 0), -1)
            # Add label
            cv2.putText(frame, "BOTTLE", (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            with self._lock:
                self._frame = frame.copy()

            # Sleep to maintain FPS
            elapsed = time.time() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def get_frame(self) -> Optional[Any]:
        """Get latest generated frame."""
        with self._lock:
            frame = self._frame
            self._frame = None  # Consume once: repeated frames are not new confirmations.
            return frame.copy() if frame is not None else None

    def stop(self) -> None:
        """Stop frame generation."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        with self._lock:
            self._frame = None
        self._logger.info("Mock camera stopped")

    def __enter__(self) -> "MockCamera":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()