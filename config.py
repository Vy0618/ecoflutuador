"""Leitura e validacao da configuracao local."""
import json
import math
from pathlib import Path


CONFIG_FILE = Path(__file__).resolve().with_name("config.json")


def load_config(path=CONFIG_FILE):
    path = Path(path).resolve()
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    camera = config["camera"]
    model = config["ssd_mobilenet"]
    processing = config["image_processing"]
    for key in ("model_path", "config_path", "labels_path"):
        model[key] = str((path.parent / model[key]).resolve())
        if not Path(model[key]).is_file():
            raise FileNotFoundError(f"Arquivo SSD MobileNet ausente: {model[key]}")
    for section, keys in ((camera, ("width", "height", "fps")),
                          (model, ("input_width", "input_height")),
                          (processing, ("max_width", "max_height"))):
        for key in keys:
            if type(section[key]) is not int or section[key] <= 0:
                raise ValueError(f"{key} deve ser um inteiro positivo")
    if type(camera["device_index"]) is not int or camera["device_index"] < 0:
        raise ValueError("camera.device_index deve ser um inteiro nao negativo")
    threshold = model["confidence_threshold"]
    if type(threshold) not in (int, float) or not 0 <= threshold <= 1:
        raise ValueError("confidence_threshold deve estar entre 0 e 1")
    interval = config["detection_interval_ms"]
    if type(interval) not in (int, float) or not math.isfinite(interval) or interval <= 0:
        raise ValueError("detection_interval_ms deve ser positivo e finito")
    targets = model["detection_types"]
    if not isinstance(targets, list) or any(not isinstance(name, str) for name in targets):
        raise ValueError("detection_types deve ser uma lista de classes")
    ratio = config["display"].setdefault("bottom_zone_ratio", 0.8)
    if type(ratio) not in (int, float) or not 0 < ratio < 1:
        raise ValueError("display.bottom_zone_ratio deve estar entre 0 e 1, sem incluir os extremos")
    if type(processing["enabled"]) is not bool:
        raise ValueError("image_processing.enabled deve ser booleano")
    navigation = config.setdefault("navigation", {})
    if not isinstance(navigation, dict):
        raise ValueError("navigation deve ser um objeto")
    for key, default, low, high in (
        ("horizontal_hysteresis_ratio", .03, 0, 1 / 6),
        ("target_min_iou", .1, 0, 1),
    ):
        value = navigation.setdefault(key, default)
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"navigation.{key} deve estar entre {low:g} e {high:g}")
    distance = navigation.setdefault("target_max_distance_px", 90)
    if type(distance) not in (int, float) or not math.isfinite(distance) or distance <= 0:
        raise ValueError("navigation.target_max_distance_px deve ser positivo e finito")
    missing = navigation.setdefault("target_missing_frames", 3)
    if type(missing) is not int or missing < 1:
        raise ValueError("navigation.target_missing_frames deve ser um inteiro positivo")
    return config
