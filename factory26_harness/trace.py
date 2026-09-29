from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import time
import zipfile
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
    # "basic application capability". Structured Authorization fields are
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
EVIDENCE_ARCHIVE_NAME = "factory26-evidence.zip"
MAX_EXPORT_TRACE_BYTES = 512_000_000
MAX_EXPORT_ROW_BYTES = 8_000_000

# ARC-Bench's project download omits .arc/. Mirror only operational evidence,
# never prompts, source bodies, model responses or request arguments, to stdout.
_PROGRESS_EVENTS = {
    "run_started", "run_completed", "run_failed",
    "implementation_batch_started", "implementation_batch_finished",
    "implementation_batch_exception", "implementation_batch_split",
    "implementation_dependency_blocked", "implementation_candidate_validation",
    "agent_session_started", "agent_session_completed", "agent_session_stalled",
    "agent_session_exhausted", "model_output_truncated", "model_gateway_circuit_open",
    "agent_context_compacted",
    "harness_graph_transition", "harness_fallback_started",
    "harness_fallback_finished", "harness_fallback_validation",
}
_PROGRESS_FIELDS = {
    "batch", "attempt", "stage", "requirement_ids", "completed", "changed_files",
    "turns", "turn", "reason", "error", "summary", "status", "split_depth",
    "retry_groups", "failed_dependencies", "checks", "phase", "consecutive",
    "model_requests", "staged_changes_committed", "browser_probe",
    "before_characters", "after_characters", "retained_current_turn",
    "fresh_observation_messages", "soft_limit_exceeded",
    "retained_specification_ids",
    "source_snapshot_bytes", "source_snapshot_files", "source_snapshot_complete_files",
    "event", "graph_event", "next_state", "previous_state", "fallback", "passed", "applied",
    "covered_ids", "fallback_available", "context_version",
}


def _public_progress_fields(payload: dict[str, Any]) -> dict[str, Any]:
    selected = {key: value for key, value in payload.items() if key in _PROGRESS_FIELDS}
    if isinstance(selected.get("checks"), list):
        selected["checks"] = [
            {**check, "summary": "Regression replay details are in the sealed trace."}
            if isinstance(check, dict) and check.get("name") == "behavior_regression"
            else check for check in selected["checks"]
        ]
    return selected


def _progress_projection(event: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    # Keep request/response bodies in the sealed trace only. These small fields
    # distinguish model latency/retries from an agent that stopped making work.
    model_fields = {
        "model_http_attempt": ("request_number", "attempt", "max_attempts", "timeout_seconds"),
        "model_response": ("finish_reason", "elapsed_seconds"),
        "model_error": (
            "attempt", "http_status", "error_type", "error_category", "retryable", "will_retry",
            "retry_delay_seconds", "retry_after_exceeds_limit", "elapsed_seconds",
            "error_categories", "error_sources", "error_body_format",
            "error_body_bytes_observed", "error_body_truncated",
        ),
        "model_budget_exhausted": (
            "request_count", "maximum_requests", "total_prompt_tokens",
            "total_completion_tokens", "maximum_prompt_tokens", "maximum_completion_tokens",
        ),
    }
    if event in model_fields:
        selected = {key: payload[key] for key in model_fields[event] if key in payload}
        if event == "model_response" and isinstance(payload.get("usage"), dict):
            selected["usage"] = {
                key: payload["usage"][key] for key in ("prompt_tokens", "completion_tokens")
                if key in payload["usage"]
            }
        return {"event": event, **selected}
    if event in {"visual_reference_response", "visual_reference_error"}:
        selected = {key: payload[key] for key in (
            "error_type", "error_category", "finish_reason", "usage_status",
            "response_bytes", "http_status",
        ) if key in payload}
        if isinstance(payload.get("usage"), dict):
            selected["usage"] = {
                key: payload["usage"][key] for key in ("prompt_tokens", "completion_tokens")
                if key in payload["usage"]
            }
        return {"event": event, **selected}
    if event == "tool_result":
        result = payload.get("result")
        if not isinstance(result, dict):
            return None
        selected = {
            key: result[key] for key in (
                "ok", "error", "path", "changed", "change_revision", "checks",
                "current_changes_validated", "assertion_failures", "page_errors",
                "requirement_id", "start_char", "next_start_char", "complete",
            ) if key in result
        }
        return {"event": event, "tool": payload.get("tool"), "result": selected}
    if event == "regression_check":
        return {"event": event, **{key: payload[key] for key in (
            "phase", "status", "check_id", "final", "capsule_count", "capsule_id",
            "selected_ids", "unselected_ids", "failed_ids", "source_status",
        ) if key in payload}}
    if event in _PROGRESS_EVENTS:
        return {"event": event, **_public_progress_fields(payload)}
    return None


def _bounded_progress(value: Any) -> Any:
    if isinstance(value, str):
        return value if len(value) <= 900 else value[:900] + " [truncated]"
    if isinstance(value, dict):
        return {key: _bounded_progress(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_bounded_progress(item) for item in value[:12]]
    return value


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
    def __init__(self, path: Path, *, stdout_progress: bool = False) -> None:
        self.path = path
        self.stdout_progress = stdout_progress
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
            if self.stdout_progress:
                progress = _progress_projection(event, row["payload"])
                if progress is not None:
                    progress["sequence"] = self._sequence
                    try:
                        print("[factory26:event] " + json.dumps(
                            _bounded_progress(progress), ensure_ascii=True, sort_keys=True
                        ), flush=True)
                    except (BrokenPipeError, OSError):
                        # Console delivery must not change the persisted run outcome.
                        self.stdout_progress = False

    def export_evidence(self, report: dict[str, Any]) -> dict[str, Any]:
        """Export existing redacted evidence, not reconstructed model activity.

        The platform omits .arc from project downloads. Keep this archive at the
        output root, outside frontend/dist and the model's writable app trees.
        Hold the trace lock through verification and copying so its head agrees.
        """
        with self._lock:
            root = self.path.parent.parent
            target = root / EVIDENCE_ARCHIVE_NAME
            if self.path.parent.is_symlink() or self.path.is_symlink():
                raise RuntimeError("evidence export requires a regular trace path")
            if target.exists() or target.is_symlink():
                raise RuntimeError("evidence archive already exists")
            redacted_report = _redact(report)
            if find_unredacted_secrets(redacted_report):
                raise RuntimeError("evidence report failed redaction verification")
            report_bytes = _canonical(redacted_report) + b"\n"
            with tempfile.NamedTemporaryFile(
                dir=root, prefix=".factory26-evidence-", suffix=".zip", delete=False,
            ) as handle:
                temporary = Path(handle.name)
            try:
                with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
                    with archive.open("production-trace.jsonl", "w") as destination:
                        metadata = _inspect_export_trace(self.path, destination)
                    if metadata["rows"] != self._sequence or metadata["head"] != self._previous_hash:
                        raise RuntimeError("evidence trace no longer matches the writer checkpoint")
                    manifest = {
                        "schema": "langqi-forge-evidence-v1",
                        "trace": metadata,
                        "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
                        "run_id": redacted_report.get("run_id"),
                        "status": redacted_report.get("status"),
                        "source": redacted_report.get("source"),
                        "independent_gui_evaluation_included": False,
                        "note": "Exact sealed trace snapshot; operational evidence is not an official score.",
                    }
                    archive.writestr("harness-report.json", report_bytes)
                    archive.writestr("evidence-manifest.json", _canonical(manifest) + b"\n")
                archive_digest = hashlib.sha256()
                with temporary.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(65_536), b""):
                        archive_digest.update(chunk)
                archive_hash = archive_digest.hexdigest()
                size = temporary.stat().st_size
                # Atomic create-if-absent: unlike replace(), a concurrent
                # exporter cannot overwrite an archive created after preflight.
                os.link(temporary, target, follow_symlinks=False)
            finally:
                temporary.unlink(missing_ok=True)
            return {
                "status": "exported", "path": EVIDENCE_ARCHIVE_NAME,
                "sha256": archive_hash, "bytes": size, "trace": metadata,
            }


def _inspect_export_trace(path: Path, destination: Any) -> dict[str, Any]:
    """Verify bounded rows in a stream; never load the entire long run in RAM."""
    previous = "GENESIS"
    count = size = 0
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while line := handle.readline(MAX_EXPORT_ROW_BYTES + 1):
            size += len(line)
            if len(line) > MAX_EXPORT_ROW_BYTES or size > MAX_EXPORT_TRACE_BYTES:
                raise RuntimeError("evidence trace exceeds export limits")
            row = json.loads(line)
            count += 1
            if not isinstance(row, dict) or (
                row.get("sequence") != count
                or row.get("trace_version") != 2
                or row.get("previous_hash") != previous
            ):
                raise RuntimeError("evidence trace sequence or chain is invalid")
            candidate = {key: value for key, value in row.items() if key != "hash"}
            expected = hashlib.sha256(_canonical(candidate)).hexdigest()
            if row.get("hash") != expected or find_unredacted_secrets(row):
                raise RuntimeError("evidence trace integrity or redaction is invalid")
            previous = expected
            digest.update(line)
            # Copy exactly the bytes just verified, never reopen the mutable
            # source later. A failure leaves only the private temporary archive.
            destination.write(line)
    if not count:
        raise RuntimeError("cannot export an empty trace")
    return {"rows": count, "bytes": size, "sha256": digest.hexdigest(), "head": previous}
