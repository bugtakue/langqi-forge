from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path
from typing import Any


_SENSITIVE_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "access_token",
    "secret",
    "password",
    "passwd",
    "credential",
    "cookie",
    "session",
    "private_key",
    "client_secret",
    "access_key",
    "connection_string",
    "database_url",
    "dsn",
    "header",
)
_SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/=]{12,}"),
    # A bare ``Basic <word>`` pattern corrupts ordinary prose such as
    # "basic spreadsheet capability".  Structured Authorization fields are
    # already redacted by key; this text rule is intentionally limited to an
    # actual HTTP header rendering.
    re.compile(r"(?i)\bAuthorization\s*:\s*Basic\s+[A-Za-z0-9+/=]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}"),
    re.compile(
        r"(?i)\b(?:OPENAI_API_KEY|DASHSCOPE_API_KEY|API_KEY|ACCESS_TOKEN|"
        r"PASSWORD|DATABASE_PASSWORD|PASSWD|CLIENT_SECRET|ACCESS_KEY|PRIVATE_KEY|DATABASE_URL|"
        r"CONNECTION_STRING|DSN|X-API-KEY)\b\s*[:=]\s*"
        r"(?:\"[^\"\r\n]+\"|'[^'\r\n]+'|[^\s,;]+)"
    ),
    re.compile(r"(?i)\b(?:Cookie|Set-Cookie)\s*:\s*[^\r\n]+"),
    re.compile(
        r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|rediss|"
        r"amqp|amqps)://[^\s/@:]+:[^\s/@]+@[^\s]+"
    ),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\." r"[A-Za-z0-9_-]{8,}\b"),
    re.compile(
        r"\b(?:gh[opsu]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|" r"LTAI[A-Za-z0-9]{12,})\b"
    ),
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


def _sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
    return any(part in normalized for part in _SENSITIVE_PARTS)


def find_unredacted_secrets(value: Any) -> list[dict[str, str]]:
    """Return locations and rule classes without echoing secret values."""

    findings: list[dict[str, str]] = []

    def walk(current: Any, path: str, key: str = "") -> None:
        if key and _sensitive_key(key) and current != "[REDACTED]":
            findings.append({"path": path, "reason": "sensitive-key"})
            return
        if isinstance(current, dict):
            for child_key, child_value in current.items():
                rendered_key = str(child_key)
                child_path = f"{path}.{rendered_key}" if path else rendered_key
                walk(child_value, child_path, rendered_key)
            return
        if isinstance(current, (list, tuple)):
            for index, child_value in enumerate(current):
                walk(child_value, f"{path}[{index}]")
            return
        if isinstance(current, str) and current != "[REDACTED]":
            for index, pattern in enumerate(_SECRET_TEXT_PATTERNS):
                if pattern.search(current):
                    findings.append(
                        {"path": path or "$", "reason": f"text-rule-{index + 1}"}
                    )
                    break

    walk(value, "$")
    return findings


def _redact(value: Any, key: str = "") -> Any:
    if _sensitive_key(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(child_key): _redact(child_value, str(child_key))
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def redact_sensitive_data(value: Any) -> Any:
    """Return the same deterministic redaction projection used by traces.

    Release artifacts that are cross-bound to a trace must persist this
    projection too; otherwise a model-produced secret could leak in the
    artifact and the redacted trace would no longer match it byte-for-byte.
    """

    return _redact(value)


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
