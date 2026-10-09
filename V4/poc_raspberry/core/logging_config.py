"""Escaped JSON events; optional bounded rotating file, never image payloads."""
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload={"timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                 "level": record.levelname, "logger": record.name, "message": record.getMessage()}
        if hasattr(record, "event"):
            payload["event"] = record.event
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, allow_nan=False)


def setup_logging(config):
    settings=config.get("logging", {})
    handlers=[logging.StreamHandler()]
    if settings.get("file"):
        handlers.append(RotatingFileHandler(settings["file"], maxBytes=2_000_000, backupCount=3, encoding="utf-8"))
    for handler in handlers:
        handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=settings.get("level","INFO").upper(), handlers=handlers, force=True)
