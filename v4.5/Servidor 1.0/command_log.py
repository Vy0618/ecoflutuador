"""Histórico limitado de mensagens, compartilhado por threads."""
from collections import deque
from threading import Lock
import time


class CommandLog:
    def __init__(self, capacity=20):
        self._entries = deque(maxlen=capacity)
        self._lock = Lock()

    def register(self, message):
        with self._lock:
            self._entries.append(f"[{time.strftime('%H:%M:%S')}] {message}")

    def snapshot(self):
        with self._lock:
            return list(self._entries)
