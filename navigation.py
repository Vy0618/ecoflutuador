"""Acompanhamento de um alvo e decisao de aproximacao e parada."""
from dataclasses import dataclass

from detection.types import Detection
from regions import match_target, regions_for_frame, target_order, valid_targets


COMMANDS = {"esquerda": "d", "baixo": "s", "meio": "w", "direita": "a"}


@dataclass(frozen=True)
class NavigationResult:
    region: str | None
    command: str
    selected: Detection | None
    changed: bool
    state: str = "aproximando"
    approach_complete: bool = False


class Navigation:
    def __init__(self, bottom_zone_ratio=0.8, horizontal_hysteresis_ratio=.03,
                 target_max_distance_px=90, target_min_iou=.1, target_missing_frames=3,
                 allowed_classes=("bottle",)):
        self.allowed_classes = set(allowed_classes)
        self.bottom_zone_ratio = bottom_zone_ratio
        self.horizontal_hysteresis_ratio = horizontal_hysteresis_ratio
        self.target_max_distance_px = target_max_distance_px
        self.target_min_iou = target_min_iou
        self.target_missing_frames = target_missing_frames
        self.previous_command = None
        self.target = None
        self.missing_frames = 0
        self.horizontal_region = None
        self.approach_complete = False

    def _result(self, region, command, selected, state):
        result = NavigationResult(region, command, selected, command != self.previous_command,
                                  state, self.approach_complete)
        self.previous_command = command
        return result

    def _horizontal(self, x, regions):
        margin = regions.width * self.horizontal_hysteresis_ratio
        first, second = regions.first_x, regions.second_x
        previous = self.horizontal_region
        if previous == "esquerda":
            first += margin
            second += margin
        elif previous == "direita":
            first -= margin
            second -= margin
        elif previous == "meio":
            first -= margin
            second += margin

        if x < first:
            region = "esquerda"
        elif x > second:
            region = "direita"
        else:
            region = "meio"
        self.horizontal_region = region
        return region

    def update(self, detections, width, height):
        regions = regions_for_frame(width, height, self.bottom_zone_ratio)
        candidates = valid_targets(detections, width, height, self.allowed_classes)
        if self.target is None:
            # Maior caixa, com desempate independente da ordem das deteccoes.
            selected = min(candidates, key=target_order, default=None)
        else:
            selected = match_target(self.target, candidates, self.target_max_distance_px, self.target_min_iou)
        if selected is None:
            state = "alvo_perdido" if self.target is not None else "sem_alvo"
            if self.target is not None:
                self.missing_frames += 1
                if self.missing_frames >= self.target_missing_frames:
                    self.target = None
                    self.missing_frames = 0
                    self.approach_complete = False
                    self.horizontal_region = None
            return self._result(None, "s", None, state)

        self.target = selected
        self.missing_frames = 0
        region = "baixo" if selected.centroid[1] >= regions.line_y else self._horizontal(selected.centroid[0], regions)
        if region == "baixo":
            self.approach_complete = True
        if self.approach_complete:
            return self._result(region, "s", selected, "aproximacao_encerrada")
        return self._result(region, COMMANDS[region], selected, "aproximando")

    def stop(self):
        return self._result(None, "s", None, "parado")


def record_navigation(log, result, detections, event="reconhecimento", mode="terminal"):
    target = result.selected
    log.record(evento=event, regiao=result.region or "sem_alvo",
               comando=result.command, mudou_comando=result.changed,
               objeto=None if target is None else target.class_name,
               confianca=None if target is None else round(target.confidence, 3),
               caixa=None if target is None else list(target.bbox),
               centro=None if target is None else list(target.centroid),
               ymax=None if target is None else target.bbox[3],
               estado=result.state, aproximacao_encerrada=result.approach_complete,
               garrafas_detectadas=sum(item.class_name == "bottle" for item in detections), modo=mode)
