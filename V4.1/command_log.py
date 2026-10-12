"""Registros JSON por inferencia no terminal e em arquivo com rotacao."""
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys


class CommandLog:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.Logger("v41.commands", level=logging.INFO)
        console = logging.StreamHandler(sys.stdout)
        file = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        for handler in (console, file):
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)
        self.sequence = 0

    def record(self, **fields):
        self.sequence += 1
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(),
                   "registro": self.sequence, **fields}
        self.logger.info(json.dumps(payload, ensure_ascii=False, allow_nan=False))
        return payload

    def close(self):
        for handler in list(self.logger.handlers):
            handler.close()
            self.logger.removeHandler(handler)
