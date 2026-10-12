"""Resumo das deteccoes no terminal e registros JSON em arquivo com rotacao."""
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
from zoneinfo import ZoneInfo


CONSOLE_FIELDS = ("regiao", "objeto", "garrafas_detectadas", "comando")


class DetectionConsoleFormatter(logging.Formatter):
    def format(self, record):
        payload = record.payload
        timestamp = datetime.fromisoformat(payload["timestamp"]).astimezone(
            ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d-%H-%S")
        lines = [f"timestamp: {timestamp}"]
        lines.extend(f"{key}: {payload[key] if payload[key] is not None else 'nenhum'}"
                     for key in CONSOLE_FIELDS)
        return "\n".join(lines) + "\n"


class CommandLog:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.Logger("v41.commands", level=logging.INFO)
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(DetectionConsoleFormatter())
        console.addFilter(lambda record: all(key in record.payload for key in CONSOLE_FIELDS))
        file = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        file.setFormatter(logging.Formatter("%(message)s"))
        for handler in (console, file):
            self.logger.addHandler(handler)
        self.sequence = 0

    def record(self, **fields):
        self.sequence += 1
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(),
                   "registro": self.sequence, **fields}
        self.logger.info(json.dumps(payload, ensure_ascii=False, allow_nan=False),
                         extra={"payload": payload})
        return payload

    def close(self):
        for handler in list(self.logger.handlers):
            handler.close()
            self.logger.removeHandler(handler)
