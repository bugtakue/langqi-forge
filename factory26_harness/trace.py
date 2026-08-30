from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any


_SENSITIVE_PARTS = ("api_key", "apikey", "authorization", "access_token", "secret")


def _redact(value: Any, key: str = "") -> Any:
    lowered = key.lower()
    if any(part in lowered for part in _SENSITIVE_PARTS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(child_key): _redact(child_value, str(child_key)) for child_key, child_value in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    return value


class ProductionTrace:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if self.path.is_file():
            try:
                self._sequence = sum(1 for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip())
            except OSError:
                self._sequence = 0
        else:
            self._sequence = 0

    def record(self, event: str, **payload: Any) -> None:
        with self._lock:
            self._sequence += 1
            row = {
                "sequence": self._sequence,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "event": event,
                "payload": _redact(payload),
            }
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
