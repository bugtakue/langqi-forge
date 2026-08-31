from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path
from typing import Any


_SENSITIVE_PARTS = ("api_key", "apikey", "authorization", "access_token", "secret")
_SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/=]{12,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}"),
    re.compile(
        r"(?i)\b(?:OPENAI_API_KEY|DASHSCOPE_API_KEY|API_KEY|ACCESS_TOKEN)\s*=\s*[^\s\"']+"
    ),
    re.compile(r"\b(?:gh[opsu]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})\b"),
    re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
)
MAX_TRACE_STRING_CHARS = 100_000


def _redact_text(value: str) -> str:
    redacted = value
    for pattern in _SECRET_TEXT_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    if len(redacted) > MAX_TRACE_STRING_CHARS:
        digest = hashlib.sha256(redacted.encode("utf-8")).hexdigest()
        redacted = (
            redacted[:MAX_TRACE_STRING_CHARS]
            + f"\n[TRUNCATED sha256={digest} original_chars={len(redacted)}]"
        )
    return redacted


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
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _legacy_anchor(row: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(row)).hexdigest()


def reseal_trace_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sealed = []
    previous_hash = "GENESIS"
    for source in rows:
        row = {
            key: value
            for key, value in source.items()
            if key not in {"hash", "previous_hash", "trace_version"}
        }
        row["trace_version"] = 2
        row["previous_hash"] = previous_hash
        row["hash"] = hashlib.sha256(_canonical(row)).hexdigest()
        previous_hash = row["hash"]
        sealed.append(row)
    return sealed


def verify_trace_rows(
    rows: list[dict[str, Any]], *, require_fully_sealed: bool = False
) -> dict[str, Any]:
    previous_hash = "GENESIS"
    sealed_rows = 0
    sealed_started = False
    for index, row in enumerate(rows, 1):
        if row.get("trace_version") != 2:
            if require_fully_sealed:
                return {
                    "valid": False,
                    "row": index,
                    "reason": "unsealed trace row",
                    "sealed_rows": sealed_rows,
                }
            if sealed_started:
                return {
                    "valid": False,
                    "row": index,
                    "reason": "trace version downgrade",
                    "sealed_rows": sealed_rows,
                }
            previous_hash = _legacy_anchor(row)
            continue
        sealed_started = True
        sealed_rows += 1
        if row.get("previous_hash") != previous_hash:
            return {
                "valid": False,
                "row": index,
                "reason": "previous hash mismatch",
                "sealed_rows": sealed_rows,
            }
        candidate = {key: value for key, value in row.items() if key != "hash"}
        expected = hashlib.sha256(_canonical(candidate)).hexdigest()
        if row.get("hash") != expected:
            return {
                "valid": False,
                "row": index,
                "reason": "row hash mismatch",
                "sealed_rows": sealed_rows,
            }
        previous_hash = expected
    if require_fully_sealed and sealed_rows != len(rows):
        return {
            "valid": False,
            "row": sealed_rows + 1,
            "reason": "trace is not fully sealed",
            "sealed_rows": sealed_rows,
        }
    return {
        "valid": True,
        "rows": len(rows),
        "sealed_rows": sealed_rows,
        "head": previous_hash,
    }


class ProductionTrace:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._sequence = 0
        self._previous_hash = "GENESIS"
        if self.path.is_file():
            rows = []
            try:
                with self.path.open(encoding="utf-8") as handle:
                    rows = [json.loads(line) for line in handle if line.strip()]
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError("production trace is unreadable") from exc
            sequences = [row.get("sequence") for row in rows]
            if sequences != list(range(1, len(rows) + 1)):
                raise RuntimeError("production trace sequence is not contiguous")
            verification = verify_trace_rows(rows)
            if not verification["valid"]:
                raise RuntimeError(
                    f"production trace integrity failed at row {verification.get('row')}"
                )
            self._sequence = len(rows)
            self._previous_hash = str(verification["head"])

    def record(self, event: str, **payload: Any) -> None:
        with self._lock:
            self._sequence += 1
            row = {
                "sequence": self._sequence,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "event": event,
                "payload": _redact(payload),
                "trace_version": 2,
                "previous_hash": self._previous_hash,
            }
            row["hash"] = hashlib.sha256(_canonical(row)).hexdigest()
            self._previous_hash = row["hash"]
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
