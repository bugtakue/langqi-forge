from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

from .checks import (
    frontend_build_check,
    package_policy_check,
    run_full_checks,
    structure_check,
)
from .trace import ProductionTrace


EXCLUDED_PARTS = {".arc", ".git", "node_modules", "dist", "coverage", "__pycache__"}
WRITABLE_ROOTS = {"frontend", "backend"}
SENSITIVE_NAMES = {".npmrc", ".pypirc", "credentials", "credentials.json"}
VALIDATING_SCOPES = {"quick", "full"}
MAX_TOOL_RESULT_CHARS = 12_000
MAX_READ_FILE_BYTES = 2_000_000
MAX_BATCH_READ_FILES = 8
MAX_BATCH_READ_BYTES = 10_000


def _contains_sensitive_part(parts: tuple[str, ...]) -> bool:
    return any(
        part.lower() in SENSITIVE_NAMES
        or part.lower() == ".env"
        or part.lower().startswith(".env.")
        or part.lower().endswith((".pem", ".key", ".p12", ".pfx"))
        for part in parts
    )


class WorkspaceTools:
    def __init__(self, root: Path, trace: ProductionTrace, smoke_port: int) -> None:
        self.root = root.resolve()
        self.trace = trace
        self.smoke_port = smoke_port
        self.changed_files: set[str] = set()
        self.change_revision = 0
        self.validated_revision = -1
        self.validation_scope = ""
        self.last_validation_passed = False
        self.write_operations = 0
        self.bytes_written = 0
        self.maximum_changed_files = max(
            1, int(os.environ.get("FACTORY26_MAX_CHANGED_FILES", "12"))
        )
        self.maximum_write_bytes = max(
            1, int(os.environ.get("FACTORY26_MAX_WRITE_BYTES", "2000000"))
        )

    @property
    def current_changes_validated(self) -> bool:
        return (
            self.last_validation_passed
            and self.validation_scope in VALIDATING_SCOPES
            and self.validated_revision == self.change_revision
        )

    @staticmethod
    def schemas() -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": "List project files without node_modules, dist, .git, or generated caches.",
                    "parameters": {
                        "type": "object",
                        "properties": {"directory": {"type": "string", "description": "Relative directory, default ."}},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a bounded range from a UTF-8 project file.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "start_line": {"type": "integer", "minimum": 1},
                            "end_line": {"type": "integer", "minimum": 1},
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_files",
                    "description": (
                        "Read up to eight small UTF-8 project files in one call. "
                        "Prefer this over serial read_file calls when the paths are already known."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 1,
                                "maxItems": MAX_BATCH_READ_FILES,
                                "uniqueItems": True,
                            }
                        },
                        "required": ["paths"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_text",
                    "description": "Search text in source files and return path, line number, and matching line.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "directory": {"type": "string", "description": "Relative directory, default ."},
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Create or fully replace one UTF-8 source file under frontend/ or backend/.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                            "expected_sha256": {
                                "type": "string",
                                "description": "Required when replacing an existing file; obtain it from read_file.",
                            },
                        },
                        "required": ["path", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "replace_text",
                    "description": "Replace exact text in one frontend/ or backend/ source file. Fails unless expected_count matches.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "old": {"type": "string"},
                            "new": {"type": "string"},
                            "expected_count": {"type": "integer", "minimum": 1, "default": 1},
                        },
                        "required": ["path", "old", "new"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "run_validation",
                    "description": "Run a safe deterministic check. Use quick during implementation and full only at batch/final boundaries.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "scope": {"type": "string", "enum": ["structure", "quick", "full"]}
                        },
                        "required": ["scope"],
                    },
                },
            },
        ]

    def _safe_path(self, relative: str, *, writable: bool = False) -> Path:
        candidate = Path(str(relative or "."))
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("path must stay inside the project")
        if any(
            ord(character) < 32 or ord(character) == 127
            for part in candidate.parts
            for character in part
        ):
            raise ValueError("path contains control characters")
        resolved = (self.root / candidate).resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise ValueError("path escapes the project")
        relative_parts = resolved.relative_to(self.root).parts
        if any(part in EXCLUDED_PARTS for part in relative_parts):
            raise ValueError("generated or control directories are not accessible")
        if _contains_sensitive_part(relative_parts):
            raise ValueError("credential-bearing files are not accessible")
        if writable and (not relative_parts or relative_parts[0] not in WRITABLE_ROOTS):
            raise ValueError("writes are limited to frontend/ and backend/")
        return resolved

    def _write_budget(self, relative: str, byte_count: int) -> None:
        new_file_count = len(self.changed_files | {relative})
        if new_file_count > self.maximum_changed_files:
            raise ValueError(
                f"changed-file budget exceeded: {new_file_count} > {self.maximum_changed_files}"
            )
        if self.bytes_written + byte_count > self.maximum_write_bytes:
            raise ValueError(
                "cumulative write budget exceeded: "
                f"{self.bytes_written + byte_count} > {self.maximum_write_bytes} bytes"
            )

    def _record_write(self, relative: str, byte_count: int) -> None:
        self.changed_files.add(relative)
        self.change_revision += 1
        self.write_operations += 1
        self.bytes_written += byte_count
        self.last_validation_passed = False
        self.validation_scope = ""

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        self.trace.record("tool_call", tool=name, arguments=arguments)
        try:
            method = getattr(self, f"_tool_{name}")
        except AttributeError:
            result = {"ok": False, "error": f"unknown tool: {name}"}
        else:
            try:
                result = method(arguments)
            except Exception as exc:  # tool errors are returned to the model
                result = {"ok": False, "error": str(exc)}
        self.trace.record("tool_result", tool=name, result=result)
        encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)
        if len(encoded) <= MAX_TOOL_RESULT_CHARS:
            return encoded
        summary = {
            "ok": bool(result.get("ok")) if isinstance(result, dict) else False,
            "truncated": True,
            "original_chars": len(encoded),
            "preview": encoded[: MAX_TOOL_RESULT_CHARS - 500],
        }
        return json.dumps(summary, ensure_ascii=False, sort_keys=True)

    def _tool_list_files(self, arguments: dict[str, Any]) -> dict[str, Any]:
        directory = self._safe_path(str(arguments.get("directory") or "."))
        files = []
        if directory.is_file():
            files = [str(directory.relative_to(self.root))]
        elif directory.is_dir():
            for path in sorted(directory.rglob("*")):
                if not path.is_file():
                    continue
                relative = path.relative_to(self.root)
                if any(part in EXCLUDED_PARTS for part in relative.parts) or _contains_sensitive_part(relative.parts):
                    continue
                files.append(str(relative))
                if len(files) >= 300:
                    break
        return {"ok": True, "files": files}

    def _tool_read_file(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = self._safe_path(str(arguments["path"]))
        file_size = path.stat().st_size
        if file_size > MAX_READ_FILE_BYTES:
            raise ValueError(
                f"file exceeds {MAX_READ_FILE_BYTES} byte read safety limit"
            )
        start = max(1, int(arguments.get("start_line") or 1))
        requested_end = int(arguments.get("end_line") or (start + 399))
        end = min(requested_end, start + 399)
        lines = path.read_text(encoding="utf-8").splitlines()
        selected = [f"{index}: {lines[index - 1]}" for index in range(start, min(end, len(lines)) + 1)]
        content = path.read_bytes()
        return {
            "ok": True,
            "path": str(path.relative_to(self.root)),
            "content": "\n".join(selected),
            "sha256": hashlib.sha256(content).hexdigest(),
            "total_lines": len(lines),
        }

    def _tool_read_files(self, arguments: dict[str, Any]) -> dict[str, Any]:
        requested = arguments.get("paths")
        if not isinstance(requested, list) or not 1 <= len(requested) <= MAX_BATCH_READ_FILES:
            raise ValueError(
                f"paths must contain between 1 and {MAX_BATCH_READ_FILES} files"
            )
        if any(not isinstance(item, str) or not item.strip() for item in requested):
            raise ValueError("every batch read path must be a non-empty string")

        normalized: list[str] = []
        total_bytes = 0
        for item in requested:
            path = self._safe_path(item)
            relative = str(path.relative_to(self.root))
            if relative in normalized:
                raise ValueError("batch read paths must be unique after normalization")
            file_size = path.stat().st_size
            total_bytes += file_size
            normalized.append(relative)
        if total_bytes > MAX_BATCH_READ_BYTES:
            raise ValueError(
                "batch read exceeds bounded context budget: "
                f"{total_bytes} > {MAX_BATCH_READ_BYTES} bytes"
            )

        return {
            "ok": True,
            "files": [self._tool_read_file({"path": path}) for path in normalized],
            "file_count": len(normalized),
            "total_bytes": total_bytes,
        }

    def _tool_search_text(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments["query"])
        if len(query) > 200:
            raise ValueError("query too long")
        matcher = re.compile(re.escape(query), re.IGNORECASE)
        directory = self._safe_path(str(arguments.get("directory") or "."))
        matches: list[dict[str, Any]] = []
        paths = [directory] if directory.is_file() else sorted(directory.rglob("*"))
        for path in paths:
            relative_parts = path.relative_to(self.root).parts
            if (
                not path.is_file()
                or any(part in EXCLUDED_PARTS for part in relative_parts)
                or _contains_sensitive_part(relative_parts)
            ):
                continue
            try:
                if path.stat().st_size > MAX_READ_FILE_BYTES:
                    continue
            except OSError:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for index, line in enumerate(lines, 1):
                if matcher.search(line):
                    matches.append({"path": str(path.relative_to(self.root)), "line": index, "text": line[:300]})
                    if len(matches) >= 80:
                        return {"ok": True, "matches": matches, "truncated": True}
        return {"ok": True, "matches": matches, "truncated": False}

    def _tool_write_file(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = self._safe_path(str(arguments["path"]), writable=True)
        content = str(arguments["content"])
        encoded = content.encode("utf-8")
        if len(encoded) > 750_000:
            raise ValueError("file content exceeds 750KB")
        if path.exists():
            expected = str(arguments.get("expected_sha256") or "").strip().lower()
            if not expected:
                raise ValueError(
                    "expected_sha256 is required when replacing an existing file"
                )
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if expected != actual:
                raise ValueError("file changed since read_file; SHA-256 precondition failed")
            if path.read_bytes() == encoded:
                return {
                    "ok": True,
                    "path": str(path.relative_to(self.root)),
                    "bytes": len(encoded),
                    "sha256": actual,
                    "changed": False,
                    "change_revision": self.change_revision,
                }
        path.parent.mkdir(parents=True, exist_ok=True)
        relative = str(path.relative_to(self.root))
        self._write_budget(relative, len(encoded))
        self._atomic_write(path, content)
        self._record_write(relative, len(encoded))
        return {
            "ok": True,
            "path": relative,
            "bytes": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "changed": True,
            "change_revision": self.change_revision,
        }

    def _tool_replace_text(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = self._safe_path(str(arguments["path"]), writable=True)
        old = str(arguments["old"])
        new = str(arguments["new"])
        expected_count = int(arguments.get("expected_count") or 1)
        content = path.read_text(encoding="utf-8")
        count = content.count(old)
        if count != expected_count:
            raise ValueError(f"expected {expected_count} occurrence(s), found {count}")
        updated = content.replace(old, new)
        relative = str(path.relative_to(self.root))
        encoded = updated.encode("utf-8")
        if updated == content:
            return {
                "ok": True,
                "path": relative,
                "replacements": count,
                "sha256": hashlib.sha256(encoded).hexdigest(),
                "changed": False,
                "change_revision": self.change_revision,
            }
        self._write_budget(relative, len(encoded))
        self._atomic_write(path, updated)
        self._record_write(relative, len(encoded))
        return {
            "ok": True,
            "path": relative,
            "replacements": count,
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "changed": True,
            "change_revision": self.change_revision,
        }

    def _tool_run_validation(self, arguments: dict[str, Any]) -> dict[str, Any]:
        scope = str(arguments["scope"])
        if scope == "structure":
            results = [structure_check(self.root)]
        elif scope == "quick":
            results = [structure_check(self.root)]
            if results[-1].passed:
                results.append(package_policy_check(self.root))
            if results[-1].passed:
                results.append(frontend_build_check(self.root))
        elif scope == "full":
            results = run_full_checks(self.root, self.smoke_port)
        else:
            raise ValueError(f"unsupported validation scope: {scope}")
        passed = all(result.passed for result in results)
        self.last_validation_passed = passed
        if passed and scope in VALIDATING_SCOPES:
            self.validated_revision = self.change_revision
            self.validation_scope = scope
        return {
            "ok": passed,
            "checks": [result.as_dict() for result in results],
            "validated_change_revision": (
                self.validated_revision if self.current_changes_validated else None
            ),
            "current_changes_validated": self.current_changes_validated,
        }
