"""Redimensionamento de frames e restauracao das coordenadas das deteccoes."""

import cv2

from .detection.types import Detection


def prepare_frame(frame, settings):
    """Reduz o frame aos limites configurados, preservando a proporcao."""
    if not settings.get("enabled", False):
        return frame
    height, width = frame.shape[:2]
    scale = min(1.0, settings["max_width"] / width, settings["max_height"] / height)
    if scale == 1.0:
        return frame
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return cv2.resize(frame, size, interpolation=cv2.INTER_AREA)


def restore_coordinates(detections, processed_shape, capture_shape):
    """Converte as caixas para as coordenadas da imagem original."""
    if processed_shape[:2] == capture_shape[:2]:
        return detections
    scale_x = capture_shape[1] / processed_shape[1]
    scale_y = capture_shape[0] / processed_shape[0]
    return [Detection(item.class_name, item.confidence, (
        round(item.bbox[0] * scale_x), round(item.bbox[1] * scale_y),
        round(item.bbox[2] * scale_x), round(item.bbox[3] * scale_y),
    )) for item in detections]
