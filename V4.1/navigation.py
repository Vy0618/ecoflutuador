"""Decisao por centro da maior garrafa, como V3/V4, com regiao inferior."""
from dataclasses import dataclass

from detection.types import Detection
from regions import regions_for_frame, select_target


COMMANDS = {"esquerda": "a", "baixo": "s", "meio": "w", "direita": "d"}


@dataclass(frozen=True)
class NavigationResult:
    region: str | None
    command: str
    selected: Detection | None
    changed: bool


class Navigation:
    def __init__(self, bottom_zone_ratio=0.8):
        self.bottom_zone_ratio = bottom_zone_ratio
        self.previous_command = None

    def update(self, detections, width, height):
        selected = select_target(detections)
        region = None if selected is None else regions_for_frame(
            width, height, self.bottom_zone_ratio).locate(selected.centroid)
        command = "s" if region is None else COMMANDS[region]
        result = NavigationResult(region, command, selected, command != self.previous_command)
        self.previous_command = command
        return result

    def stop(self):
        result = NavigationResult(None, "s", None, self.previous_command != "s")
        self.previous_command = "s"
        return result


def record_navigation(log, result, detections, event="reconhecimento"):
    target = result.selected
    log.record(evento=event, regiao=result.region or "sem_alvo",
               comando=result.command, mudou_comando=result.changed,
               objeto=None if target is None else target.class_name,
               confianca=None if target is None else round(target.confidence, 3),
               caixa=None if target is None else list(target.bbox),
               centro=None if target is None else list(target.centroid),
               garrafas_detectadas=len(detections), modo="terminal")
