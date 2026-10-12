"""Geometria compartilhada entre as linhas da imagem e a classificacao do alvo."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Regions:
    width: int
    height: int
    line_y: int
    first_x: int
    second_x: int

    def locate(self, center):
        x, y = center
        if y >= self.line_y:
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


def select_target(detections):
    """Como V3/V4, acompanha a garrafa com maior area de caixa."""
    bottles = [item for item in detections if item.class_name == "bottle"]
    return max(bottles, key=lambda item: (item.bbox[2] - item.bbox[0]) *
               (item.bbox[3] - item.bbox[1]), default=None)
