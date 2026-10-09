"""Validated YAML, paths relative to the YAML, selected environment overrides."""
import math
import os
from pathlib import Path
import yaml


def load_config(path):
    path = Path(path).resolve()
    with path.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a YAML mapping")
    for section in ("camera", "model", "serial", "decision", "api", "performance", "recognition", "logging", "telemetry"):
        if not isinstance(config.setdefault(section, {}), dict):
            raise ValueError(f"{section} must be a mapping")
    config["serial"].setdefault("require_control_lease", True)
    config["serial"].setdefault("auto_detect", False)
    for env, section, key in (("ECO_SERIAL_PORT", "serial", "port"),
                              ("ECO_CAMERA_BACKEND", "camera", "backend"),
                              ("ECO_DETECTOR_BACKEND", "model", "backend"),
                              ("ECO_SERVER_URL", "telemetry", "server_url"),
                              ("ECO_LOG_LEVEL", "logging", "level")):
        if env in os.environ:
            config[section][key] = os.environ[env]
    for key in ("weights", "config", "classes"):
        if config["model"].get(key):
            config["model"][key] = str((path.parent / config["model"][key]).resolve())
    positive = {"camera": ("width", "height", "fps", "timeout_s"),
                "performance": ("target_fps", "max_inference_ms"),
                "recognition": ("detection_timeout_s", "telemetry_timeout_s", "window_s"),
                "serial": ("baudrate", "timeout", "heartbeat_s"),
                "decision": ("confirmation_frames",), "telemetry": ("interval_s",)}
    for section, keys in positive.items():
        for key in keys:
            value = config[section].get(key)
            if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or value <= 0):
                raise ValueError(f"{section}.{key} must be positive and finite")
    for section, keys in {"recognition": ("confirmation_s",), "decision": ("loss_timeout_s", "hysteresis_fraction"), "serial": ("reconnect_delay",)}.items():
        for key in keys:
            value=config[section].get(key, 0)
            if type(value) not in (int,float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{section}.{key} must be nonnegative and finite")
    for section, key in (("model", "conf_threshold"), ("model", "nms_threshold"), ("decision", "confidence_threshold")):
        value=config[section].get(key, .45)
        if type(value) not in (int,float) or not 0 <= value <= 1:
            raise ValueError(f"{section}.{key} must be between 0 and 1")
    for section, key in (("camera","width"),("camera","height"),("camera","index"),("decision","confirmation_frames"),("serial","baudrate"),("api","port")):
        value=config[section].get(key)
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(f"{section}.{key} must be an integer")
    if config["decision"].get("zones",3) != 3:
        raise ValueError("decision.zones must be 3")
    if config["decision"].get("default_command","s") != "s":
        raise ValueError("The safe default command must be s")
    if config["camera"].get("backend", "V4L2").upper() not in {"V4L2","PICAMERA2","ANY","DSHOW","MSMF"}:
        raise ValueError("Unsupported camera backend")
    size = config["model"].get("input_size", [320,320])
    if not isinstance(size,list) or len(size)!=2 or any(type(x) is not int or x<=0 for x in size):
        raise ValueError("model.input_size must be two positive integers")
    if config["serial"].get("heartbeat_s",.5) >= 1.5:
        raise ValueError("heartbeat_s must be below firmware lease 1.5s")
    if config["performance"].get("target_fps",10) <= 1/config["serial"].get("heartbeat_s",.5):
        raise ValueError("target_fps must allow servicing heartbeat")
    for key in ("target_classes", "fauna_classes"):
        value=config["decision"].get(key, [])
        if not isinstance(value,list) or any(not isinstance(x,str) for x in value):
            raise ValueError(f"decision.{key} must be a list of class names")
    for section,key in (("serial","auto_detect"),("serial","require_control_lease"),("decision","fauna_priority"),("api","enabled")):
        if key in config[section] and type(config[section][key]) is not bool:
            raise ValueError(f"{section}.{key} must be a boolean")
    if config["api"].get("port",8080)>65535:
        raise ValueError("api.port must be <=65535")
    if config["logging"].get("level","INFO").upper() not in {"DEBUG","INFO","WARNING","ERROR","CRITICAL"}:
        raise ValueError("Invalid logging.level")
    return config
