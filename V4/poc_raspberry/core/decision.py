"""
Decision engine for EcoFlutuador POC.
Implements zone-based navigation logic (left/center/right).
"""
import logging
import time
from typing import List, Optional
from dataclasses import dataclass
from core.contracts import Detection


@dataclass
class DecisionConfig:
    target_classes: tuple = ("bottle", "plastic_bottle", "plastic_bag")
    fauna_classes: tuple = ("fish", "turtle", "bird")
    fauna_priority: bool = True
    confidence_threshold: float = 0.45
    zones: int = 3
    default_command: str = "s"  # STOP when no detection
    send_only_on_change: bool = True
    confirmation_frames: int = 1  # legacy callers; V4 pipeline uses 3
    loss_timeout_s: float = 0.0
    hysteresis_fraction: float = 0.0
    # frame_width será obtido dinamicamente do frame (não hardcoded)


class DecisionEngine:
    """
    Zone-based navigation decision logic.
    Divides frame horizontally into zones:
    - Left zone: command 'a' (turn left)
    - Center zone: command 'w' (forward)
    - Right zone: command 'd' (turn right)
    - No detection: command 's' (stop)
    
    Zones are proportional to frame width, so they work with any resolution.
    """

    def __init__(self, config: DecisionConfig):
        self.config = config
        self._logger = logging.getLogger(__name__)
        self._last_command: Optional[str] = None
        self.previous_command = "s"
        self.last_change_timestamp = time.time()
        self.reason = "Aguardando START"
        self._candidate = None
        self._candidate_count = 0
        self._last_seen = None
        self.selected = None
        self._last_frame_id = None
        # zone_width will be calculated dynamically based on frame width

    def decide(self, detections: List[Detection], frame_width: int = 320, now=None) -> Optional[str]:
        """
        Decide navigation command based on detections.
        Returns command character: 'w', 'a', 'd', 's', 'q', 'e' or None if no change.
        
        Args:
            detections: List of Detection objects
            frame_width: Width of the frame in pixels (for proportional zones)
        """
        now = time.monotonic() if now is None else now
        if frame_width <= 0 or self.config.zones != 3:
            raise ValueError("Expected positive width and three zones")
        import math
        valid=[]
        for det in detections:
            if (len(det.bbox)!=4 or any(not math.isfinite(v) for v in det.bbox)
                or det.bbox[2]<=0 or det.bbox[3]<=0 or not math.isfinite(det.confidence)
                or not 0 <= det.confidence <= 1):
                return self.stop("Deteccao invalida")
            if det.confidence >= self.config.confidence_threshold:
                valid.append(det)
        ids={d.frame_id for d in detections if d.frame_id is not None}
        if ids:
            if len(ids)!=1 or (self._last_frame_id is not None and min(ids)<=self._last_frame_id):
                return self.stop("Frame repetido ou fora de ordem")
            self._last_frame_id=next(iter(ids))
        fauna=[d for d in valid if d.class_name in self.config.fauna_classes]
        targets=[d for d in valid if d.class_name in self.config.target_classes]
        if fauna and (self.config.fauna_priority or not targets):
            result=self.stop("Fauna: parada prioritaria")
            self.selected=max(fauna, key=lambda d:d.confidence)
            return result
        detections=targets
        self.selected=max(targets, key=lambda d:d.bbox[2]*d.bbox[3]) if targets else None
        # Calculate zone boundaries based on actual frame width
        zone_width = frame_width // self.config.zones
        
        if not detections:
            self._candidate = None
            self._candidate_count = 0
            if self._last_seen is not None and now-self._last_seen < self.config.loss_timeout_s:
                self.reason = "Perda momentanea tolerada"
                return None
            cmd = "s"
            self.reason = "Sem alvo: parada segura"
        else:
            self._last_seen = now
            # Pick detection with largest area (closest object)
            best = max(detections, key=lambda d: d.bbox[2] * d.bbox[3])
            x, y, w, h = best.bbox
            cx = x + w // 2  # center X

            # Determine zone proportionally to frame width
            if cx < zone_width:
                cmd = 'a'      # left
            elif cx > 2 * zone_width:
                cmd = 'd'      # right
            else:
                cmd = 'w'      # center

            margin = frame_width*self.config.hysteresis_fraction
            if self._last_command == 'a' and cx < zone_width+margin:
                cmd = 'a'
            elif self._last_command == 'd' and cx > 2*zone_width-margin:
                cmd = 'd'
            elif self._last_command == 'w' and zone_width-margin <= cx <= 2*zone_width+margin:
                cmd = 'w'
            if cmd != self._last_command:
                if cmd == self._candidate:
                    self._candidate_count += 1
                else:
                    self._candidate, self._candidate_count = cmd, 1
                if self._candidate_count < self.config.confirmation_frames:
                    self.reason = f"Confirmando direcao {cmd}: {self._candidate_count}/{self.config.confirmation_frames}"
                    return None
            else:
                self._candidate, self._candidate_count = None, 0
            self.reason = f"Maior alvo na zona {cmd}; direcao confirmada"

        # Only return command if changed (to avoid oscillation)
        if self.config.send_only_on_change and cmd == self._last_command:
            return None  # No change

        if cmd != self._last_command:
            self.previous_command = self._last_command or "s"
            self.last_change_timestamp = time.time()
        self._last_command = cmd
        return cmd

    def stop(self, reason="Aguardando START"):
        changed = self._last_command != "s"
        if changed:
            self.previous_command = self._last_command or "s"
            self.last_change_timestamp = time.time()
        self._last_command = "s"
        self._candidate, self._candidate_count, self._last_seen = None, 0, None
        self.reason = reason
        self.selected = None
        return "s" if changed else None

    def details(self):
        return {"previous_command": self.previous_command,
                "current_command": self._last_command or "s",
                "last_change_timestamp": self.last_change_timestamp, "reason": self.reason}

    def reset(self) -> None:
        """Reset last command (e.g., when switching modes)."""
        self.stop()
        self._last_command = None

    def get_zones(self, frame_width: int = 320) -> dict:
        """Return zone boundaries for debugging."""
        zone_width = frame_width // self.config.zones
        return {
            "left": (0, zone_width),
            "center": (zone_width, 2 * zone_width),
            "right": (2 * zone_width, frame_width),
            "zone_width": zone_width,
            "frame_width": frame_width
        }