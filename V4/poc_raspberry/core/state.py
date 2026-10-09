"""
Core state dataclass for EcoFlutuador POC.
Represents the current detection/decision state, serializable to JSON.
"""
from dataclasses import dataclass, asdict
from typing import Optional, List
import time
from enum import Enum


class OperationalState(str, Enum):
    WAITING = "WAITING"
    CONFIRMING = "CONFIRMING"
    RECOGNIZING = "RECOGNIZING"
    TRACKING = "TRACKING"
    FAULT = "FAULT"


class RecognitionController:
    """ESP32 confirms START; Pi waits a short settling interval before inference.

    A detection timeout disarms until a new rising START edge, preventing
    continuously-high telemetry from restarting recognition every loop.
    """
    def __init__(self, confirmation_s=0.1, detection_timeout_s=2.0, window_s=15.0):
        self.state = OperationalState.WAITING
        self.confirmation_s = confirmation_s
        self.detection_timeout_s = detection_timeout_s
        self.window_s = window_s
        self.start_high = False
        self.since = 0.0
        self.last_detection = None
        self.last_error = None

    @property
    def active(self):
        return self.state in (OperationalState.RECOGNIZING, OperationalState.TRACKING)

    def start_event(self, detected, now):
        rising = detected and not self.start_high
        self.start_high = detected
        if not detected:
            if self.state != OperationalState.FAULT:
                self.state = OperationalState.WAITING
            self.last_detection = None
        elif rising and self.state == OperationalState.WAITING:
            self.state = OperationalState.CONFIRMING
            self.since = now

    def tick(self, now):
        if self.state == OperationalState.CONFIRMING and now-self.since >= self.confirmation_s:
            self.state = OperationalState.RECOGNIZING
            self.since = now
            self.last_detection = None
        if self.active and now-self.since >= self.window_s:
            self.state = OperationalState.WAITING
        if self.active and now-(self.last_detection if self.last_detection is not None else self.since) >= self.detection_timeout_s:
            self.state = OperationalState.WAITING

    def detection(self, found, now):
        if self.active and found:
            self.state = OperationalState.TRACKING
            self.last_detection = now

    def fault(self, message):
        self.last_error = message
        self.state = OperationalState.FAULT
        self.start_high = False

    def recover(self):
        self.state = OperationalState.WAITING
        self.start_high = False
        self.last_detection = None


@dataclass
class DetectionState:
    """Current state of the detection and decision pipeline."""
    timestamp: float
    detected: bool
    object: Optional[str] = None
    confidence: float = 0.0
    center_x: float = 0.0
    center_y: float = 0.0
    bbox: Optional[List[int]] = None
    decision: str = "s"
    inference_ms: float = 0.0
    fps: float = 0.0
    zone: Optional[str] = None

    def to_json(self) -> dict:
        """Convert to JSON-serializable dict."""
        return asdict(self)

    @classmethod
    def empty(cls, timestamp: float = None, fps: float = 0.0) -> "DetectionState":
        """Create an empty state (no detection)."""
        return cls(
            timestamp=timestamp or time.time(),
            detected=False,
            decision="s",
            fps=fps
        )

    @classmethod
    def from_detection(cls, box: List[int], class_name: str, confidence: float,
                       decision: str, inference_ms: float, fps: float,
                       frame_width: int, frame_height: int) -> "DetectionState":
        """Create state from detection results."""
        x, y, w, h = box
        return cls(
            timestamp=time.time(),
            detected=True,
            object=class_name,
            confidence=round(confidence, 3),
            center_x=round((x + w / 2) / frame_width, 3),
            center_y=round((y + h / 2) / frame_height, 3),
            bbox=[x, y, w, h],
            zone="LEFT" if x+w//2 < frame_width//3 else "RIGHT" if x+w//2 > 2*(frame_width//3) else "CENTER",
            decision=decision,
            inference_ms=round(inference_ms, 1),
            fps=round(fps, 1)
        )
