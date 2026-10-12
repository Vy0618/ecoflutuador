"""Geometria compartilhada entre as linhas da imagem e a classificacao do alvo."""
from dataclasses import dataclass
import math

from detection.types import Detection


@dataclass(frozen=True)
class Regions:
    width: int
    height: int
    line_y: int
    first_x: int
    second_x: int

    def locate(self, center, ymax=None):
        x, y = center
        if (y if ymax is None else ymax) >= self.line_y:
            return "baixo"
        if x < self.first_x:
            return "esquerda"
        if x > self.second_x:
            return "direita"
        return "meio"


def regions_for_frame(width, height, bottom_zone_ratio=0.8):
    if width < 3 or height < 2:
        raise ValueError("Imagem pequena demais para as quatro regioes")
    if not 0 < bottom_zone_ratio < 1:
        raise ValueError("A linha horizontal deve estar dentro da imagem")
    third = width // 3
    return Regions(width, height, min(height - 1, max(1, int(height * bottom_zone_ratio))), third, 2 * third)


def valid_targets(detections, width=None, height=None):
    targets = []
    for item in detections:
        if not isinstance(item, Detection) or item.class_name != "bottle":
            continue
        try:
            x1, y1, x2, y2 = item.bbox
            finite = all(math.isfinite(value) for value in (*item.bbox, item.confidence))
            valid = (finite and 0 <= item.confidence <= 1 and
                     0 <= x1 < x2 and 0 <= y1 < y2 and
                     (width is None or x2 <= width) and
                     (height is None or y2 <= height))
        except (TypeError, ValueError):
            valid = False
        if valid:
            targets.append(item)
    return targets


def target_order(item):
    x1, y1, x2, y2 = item.bbox
    return (-(x2 - x1) * (y2 - y1), -item.confidence, x1, y1, x2, y2)


def select_target(detections):
    """Maior caixa, com desempate independente da ordem das deteccoes."""
    return min(valid_targets(detections), key=target_order, default=None)


def match_target(previous, detections, max_distance, min_iou):
    """Associa pela sobreposicao e distancia, sem trocar pela maior caixa."""
    candidates = []
    px1, py1, px2, py2 = previous.bbox
    previous_area = (px2 - px1) * (py2 - py1)
    pcx, pcy = previous.centroid
    for item in detections:
        x1, y1, x2, y2 = item.bbox
        intersection = max(0, min(px2, x2) - max(px1, x1)) * max(0, min(py2, y2) - max(py1, y1))
        area = (x2 - x1) * (y2 - y1)
        iou = intersection / (previous_area + area - intersection)
        cx, cy = item.centroid
        distance = (cx - pcx) ** 2 + (cy - pcy) ** 2
        if (iou > 0 and iou >= min_iou) or distance <= max_distance ** 2:
            candidates.append(((-iou, distance, *target_order(item)), item))
    return min(candidates, key=lambda candidate: candidate[0])[1] if candidates else None
