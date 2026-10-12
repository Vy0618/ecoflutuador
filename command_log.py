"""Resumo das deteccoes no terminal e registros JSON em arquivo com rotacao."""
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
from zoneinfo import ZoneInfo


CONSOLE_FIELDS = ("regiao", "objeto", "garrafas_detectadas", "comando")
CONSOLE_TIMEZONE = ZoneInfo("America/Sao_Paulo")


class CommandLog:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.Logger("v41.commands", level=logging.INFO)
        self.file = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        self.logger.addHandler(self.file)
        self.console = sys.stdout
        self.sequence = 0

    def record(self, **fields):
        self.sequence += 1
        now = datetime.now(timezone.utc)
        payload = {"timestamp": now.isoformat(),
                   "registro": self.sequence, **fields}
        self.logger.info(json.dumps(payload, ensure_ascii=False, allow_nan=False))
        if all(key in payload for key in CONSOLE_FIELDS):
            timestamp = now.astimezone(CONSOLE_TIMEZONE).strftime("%Y-%m-%d-%H-%S")
            lines = [f"timestamp: {timestamp}"]
            lines.extend(f"{key}: {payload[key] if payload[key] is not None else 'nenhum'}"
                         for key in CONSOLE_FIELDS)
            print("\n".join(lines) + "\n", file=self.console, flush=True)
        return payload

    def close(self):
        self.file.close()
        self.logger.removeHandler(self.file)
