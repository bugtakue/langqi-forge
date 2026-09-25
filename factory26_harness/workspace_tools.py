from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

from .browser_probe import MAX_ASSERTIONS, MAX_STEPS, SCOPE_ROLES, probe_local_app, validate_steps
from .checks import run_full_checks, run_quick_checks, structure_check
from .trace import ProductionTrace
from .visual_reference import VisualReferenceClient


EXCLUDED_PARTS = {".arc", ".git", "node_modules", "dist", "coverage", "__pycache__"}
WRITABLE_ROOTS = {"frontend", "backend"}
SENSITIVE_NAMES = {".npmrc", ".pypirc", "credentials", "credentials.json"}
VALIDATING_SCOPES = {"quick", "full"}
MAX_TOOL_RESULT_CHARS = 12_000
MAX_READ_FILE_BYTES = 2_000_000
MAX_BATCH_READ_FILES = 8
MAX_BATCH_READ_BYTES = 4_000_000
MAX_BATCH_RESULT_CONTENT_CHARS = 9_000
MAX_REQUIREMENT_PAGE_CHARS = 4_000
MAX_DIRECT_READ_RESULT_CHARS = MAX_TOOL_RESULT_CHARS - 500


def _batch_content_budgets(lengths: list[int], total_budget: int) -> list[int]:
    """Give unused small-file capacity to larger files without exceeding the batch cap."""

    budgets = [0] * len(lengths)
    remaining = total_budget
    pending = list(range(len(lengths)))
    while pending:
        share = remaining // len(pending)
        complete = [index for index in pending if lengths[index] <= share]
        if not complete:
            extra = remaining % len(pending)
            for position, index in enumerate(pending):
                budgets[index] = share + (position < extra)
            break
        for index in complete:
            budgets[index] = lengths[index]
            remaining -= lengths[index]
            pending.remove(index)
    return budgets


def _compact_browser_result(result: dict[str, Any], original_chars: int) -> str:
    """Keep probe diagnostics and the latest state within the serialized limit."""

    text_limit = 500

    def text(value: Any, limit: int | None = None) -> str:
        return value[:text_limit if limit is None else limit] if isinstance(value, str) else ""

    def items(value: Any, limit: int) -> list[Any]:
        return value[:limit] if isinstance(value, list) else []

    def texts(value: Any, limit: int) -> list[str]:
        return [text(item) for item in items(value, limit) if isinstance(item, str)]

    def number(value: Any) -> int:
        return max(0, min(value, 1_000_000_000)) if type(value) is int else 0

    observations = result.get("observations")
    latest = observations[-1] if isinstance(observations, list) and observations else None
    while True:
        summary = {
            "ok": bool(result.get("ok")),
            "truncated": True,
            "original_chars": original_chars,
            "workspace_isolated": bool(result.get("workspace_isolated")),
            "behavioral_checks": number(result.get("behavioral_checks")),
            "behavioral_assertions": number(result.get("behavioral_assertions")),
            "assertion_failures": [
                {"step": number(row.get("step")), "missing": texts(row.get("missing"), 4),
                 "unexpected": texts(row.get("unexpected"), 4)}
                for row in items(result.get("assertion_failures"), 9) if isinstance(row, dict)
            ],
            "page_errors": texts(result.get("page_errors"), 10),
            "blocked_external_hosts": texts(result.get("blocked_external_hosts"), 10),
        }
        if "error" in result:
            summary["error"] = text(result["error"])
        if isinstance(latest, dict):
            visible_text = text(latest.get("visible_text"), min(2800, text_limit * 6))
            summary["observations"] = [{
                "action": text(latest.get("action")),
                "path": text(latest.get("path")),
                "visible_text": visible_text,
                "visible_text_truncated": (
                    bool(latest.get("visible_text_truncated"))
                    or visible_text != latest.get("visible_text")
                ),
                "missing_text": texts(latest.get("missing_text"), 4),
                "unexpected_text": texts(latest.get("unexpected_text"), 4),
                "controls": [
                    {"tag": text(control.get("tag")), "role": text(control.get("role")),
                     "name": text(control.get("name")), "disabled": bool(control.get("disabled"))}
                    for control in items(latest.get("controls"), 40) if isinstance(control, dict)
                ],
            }]
            summary["observations_omitted"] = len(observations) - 1
        encoded = json.dumps(summary, ensure_ascii=False, sort_keys=True)
        if len(encoded) <= MAX_TOOL_RESULT_CHARS:
            return encoded
        # JSON escaping can expand each source character. Bound the encoded
        # result as well; the fixed schema/array caps fit even at zero text.
        text_limit //= 2


def _contains_sensitive_part(parts: tuple[str, ...]) -> bool:
    return any(
        part.lower() in SENSITIVE_NAMES
        or part.lower() == ".env"
        or part.lower().startswith(".env.")
        or part.lower().endswith((".pem", ".key", ".p12", ".pfx"))
        for part in parts
    )


class WorkspaceTools:
    def __init__(
        self,
        root: Path,
        trace: ProductionTrace,
        smoke_port: int,
        *,
        visual_client: VisualReferenceClient | None = None,
        reference_paths: tuple[str, ...] = (),
        handoff_notes: tuple[str, ...] = (),
    ) -> None:
        self.root = root.resolve()
        self.trace = trace
        self.smoke_port = smoke_port
        self.visual_client = visual_client
        self.reference_paths = tuple(sorted(set(reference_paths)))
        self.handoff_notes = handoff_notes
        self.requirement_specs: dict[str, str] = {}
        self.requirement_spec_offsets: dict[str, int] = {}
        self.inline_requirement_ids: set[str] = set()
        self.changed_files: set[str] = set()
        self.change_revision = 0
        self.validated_revision = -1
        self.validation_scope = ""
        self.last_validation_passed = False
        self.write_operations = 0
        self.bytes_written = 0
        self.browser_probe_calls = 0
        self.browser_probe_requires_recheck = False
        self.browser_probe_verified_revision = -1
        self._successful_browser_steps: list[dict[str, Any]] = []
        self._successful_browser_flows: list[list[dict[str, Any]]] = []
        self.maximum_browser_probe_calls = max(
            0, min(5, int(os.environ.get("FACTORY26_MAX_BROWSER_PROBES_PER_BATCH", "3"))))
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

    @property
    def verified_browser_steps(self) -> list[dict[str, Any]]:
        """Export an isolated copy only while the tested source revision is valid."""
        if (not self.current_changes_validated or self.browser_probe_requires_recheck
                or self.browser_probe_verified_revision != self.change_revision):
            return []
        return json.loads(json.dumps(self._successful_browser_steps))

    @property
    def verified_browser_flows(self) -> list[list[dict[str, Any]]]:
        """All distinct successful recipes on this revision, not just the last one."""
        if not self.verified_browser_steps:
            return []
        return json.loads(json.dumps(self._successful_browser_flows))

    def register_requirement_specs(self, specs: dict[str, str]) -> None:
        """Expose only abbreviated requirements assigned to the current batch."""

        if self.requirement_specs:
            raise ValueError("requirement specs were already registered for this batch")
        self.requirement_specs = dict(specs)
        self.requirement_spec_offsets = {req_id: 0 for req_id in specs}

    @property
    def requirement_specs_complete(self) -> bool:
        return all(
            self.requirement_spec_offsets.get(req_id, 0) >= len(document)
            for req_id, document in self.requirement_specs.items()
        )

    def register_inline_requirement_delivery(self, documents: dict[str, str]) -> None:
        """Harness-only receipt for exact documents included in the initial prompt.

        This method is deliberately absent from the model tool schema. A prompt
        summary or partial document cannot satisfy the complete-input gate.
        """
        for req_id, document in documents.items():
            if req_id not in self.requirement_specs or self.requirement_specs[req_id] != document:
                raise ValueError("inline specification does not match the assigned original")
        for req_id, document in documents.items():
            self.inline_requirement_ids.add(req_id)
            self.requirement_spec_offsets[req_id] = len(document)

    def requirement_spec_access_state(self) -> list[dict[str, Any]]:
        """Compact source references for restoring context after chat compression."""

        return [
            {
                "requirement_id": req_id,
                "total_chars": len(document),
                "sha256": hashlib.sha256(document.encode("utf-8")).hexdigest(),
                "next_unread_char": self.requirement_spec_offsets.get(req_id, 0),
                "initial_read_complete": (
                    self.requirement_spec_offsets.get(req_id, 0) >= len(document)
                ),
                "initial_delivery": (
                    "initial_prompt" if req_id in self.inline_requirement_ids else "paged_tool"
                ),
            }
            for req_id, document in sorted(self.requirement_specs.items())
        ]

    def _require_complete_specs(self) -> None:
        unread = sorted(
            req_id for req_id, document in self.requirement_specs.items()
            if self.requirement_spec_offsets.get(req_id, 0) < len(document)
        )
        if unread:
            raise ValueError(
                "read complete abbreviated requirement specs before editing: "
                + ", ".join(unread)
            )

    def schemas(self) -> list[dict[str, Any]]:
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": "List project files without node_modules, dist, .git, or generated caches.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "directory": {
                                "type": "string",
                                "description": "Relative directory, default .",
                            }
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": (
                        "Read up to 400 numbered lines from a UTF-8 project file. "
                        "requested_range_complete distinguishes a complete requested range "
                        "from a page cut by limits. content_truncated only means later file "
                        "text exists; read it only when relevant, not automatically to EOF. "
                        "For an oversized single line, use the returned next_start_char "
                        "with start_char to page through exact source characters."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "start_line": {"type": "integer", "minimum": 1},
                            "end_line": {"type": "integer", "minimum": 1},
                            "start_char": {
                                "type": "integer",
                                "minimum": 0,
                                "description": "Alternative exact character-page cursor for oversized lines.",
                            },
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
                        "Prefer this over serial read_file calls when the paths are already known. "
                        "If a file reports content_truncated, continue it with read_file "
                        "from next_start_line before relying on omitted code."
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
                            "directory": {
                                "type": "string",
                                "description": "Relative directory, default .",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Create or fully replace one frontend/ or backend/ UTF-8 file. Supply expected_sha256 before content.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "expected_sha256": {
                                "type": "string",
                                "description": "Latest observed read/write SHA for existing files; empty string only for a new file. Never omit.",
                            },
                            "content": {"type": "string"},
                        },
                        "required": ["path", "expected_sha256", "content"],
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
                            "expected_count": {
                                "type": "integer",
                                "minimum": 1,
                                "default": 1,
                            },
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
                            "scope": {
                                "type": "string",
                                "enum": ["structure", "quick", "full"],
                            }
                        },
                        "required": ["scope"],
                    },
                },
            },
        ]
        if self.requirement_specs:
            schemas.append({
                "type": "function",
                "function": {
                    "name": "read_requirement_spec",
                    "description": (
                        "Read the original public specification for one abbreviated "
                        "requirement in this batch, in sequential bounded pages. "
                        "Continue from next_start_char until complete=true before editing. "
                        "After the first full read, any page can be reviewed again by "
                        "start_char, including after context compression."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "requirement_id": {
                                "type": "string",
                                "enum": sorted(self.requirement_specs),
                            },
                            "start_char": {"type": "integer", "minimum": 0},
                        },
                        "required": ["requirement_id", "start_char"],
                        "additionalProperties": False,
                    },
                },
            })
        if self.maximum_browser_probe_calls:
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": "browser_probe",
                        "description": (
                            "After a passing quick validation, open only the generated local app "
                            "in Chromium. Inspect visible text/semantic controls, then optionally "
                            "click, fill, press, select, check, reload or navigate local paths. "
                            f"Use up to {MAX_STEPS} actions for one complete user workflow with visible-text assertions; "
                            "this is not a hidden-test or score oracle. At most three launches per batch. "
                            "Use steps=[] to inspect controls if names are unknown. Every call starts "
                            "from fresh seed state at /; records and sessions created in earlier calls are gone. "
                            "Keep setup, rejection/correction, success and reload "
                            "in one call when relevant. Do not omit final assertions just to shorten the plan. "
                            "For a control step choose EXACTLY ONE: role+name, label, or text. "
                            "Never combine them, nest a locator, or use CSS selectors. "
                            "Use role+name for buttons/links; label is an input's associated label, "
                            "not arbitrary visible button text. Example steps: "
                            '[{"action":"fill","label":"Name","value":"Alice"},'
                            '{"action":"click","role":"button","name":"Save",'
                            '"expect_text":["Saved: Alice"]},'
                            '{"action":"reload","expect_text":["Saved: Alice"]}]. '
                            "Take specified roles/names/assertions from requirements, not generated controls. "
                            "Repair app mismatches; never relax a locator to pass. Omit index to enforce "
                            "a unique match; specify it only for intentionally repeated items."
                            ' For legitimate duplicate controls use scope:{"role":"main"} or '
                            'a named semantic owner such as {"role":"dialog","name":"Settings"}. '
                            "The scope and target must each be unique. Assertions remain page-wide unless "
                            "expect_scope is explicitly supplied; use it to verify feedback inside its owning "
                            "form, dialog, region or row. scope locates the action, expect_scope locates "
                            "the feedback after the action, so a closing dialog needs a different feedback owner."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "steps": {
                                    "type": "array",
                                    "maxItems": MAX_STEPS,
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "action": {
                                                "type": "string",
                                                "enum": ["click", "fill", "press", "select", "check", "reload", "navigate"],
                                            },
                                            "role": {"type": "string", "description": "Accessible role, e.g. button or link. Requires name; excludes label/text."},
                                            "name": {"type": "string", "description": "Exact accessible name. Only with role."},
                                            "label": {"type": "string", "description": "Exact associated form-control label. Excludes role/text."},
                                            "text": {"type": "string", "description": "Exact visible text for click/press only. Excludes role/label."},
                                            "index": {"type": "integer", "minimum": 0, "maximum": 19, "description": "Optional explicit repeated-item position. Omit for strict unique matching."},
                                            **{
                                                key: {
                                                    "type": "object",
                                                    "description": description,
                                                    "properties": {
                                                        "role": {"type": "string", "enum": list(SCOPE_ROLES)},
                                                        "name": {"type": "string", "minLength": 1, "maxLength": 200},
                                                    },
                                                    "required": ["role"],
                                                    "additionalProperties": False,
                                                }
                                                for key, description in (
                                                    ("scope", "Unique visible semantic owner of the control, not CSS. Control actions only."),
                                                    ("expect_scope", "Unique visible semantic owner of post-action assertions, including after reload. Missing/ambiguous owner fails."),
                                                )
                                            },
                                            "path": {"type": "string", "description": "Local /path or /#/route; optional query/fragment. No absolute URL or //."},
                                            "value": {"type": "string"},
                                            "option_by": {"type": "string", "enum": ["label", "value"]},
                                            "expect_text": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_ASSERTIONS},
                                            "expect_absent": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_ASSERTIONS},
                                        },
                                        "required": ["action"],
                                    },
                                }
                            },
                            "required": ["steps"],
                            "additionalProperties": False,
                        },
                    },
                }
            )
        if self.visual_client is not None and self.reference_paths:
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": "inspect_reference",
                        "description": (
                            "Describe one organizer-provided UI screenshot explicitly named "
                            "in the current requirement batch. The image is not copied into "
                            "the generated app. Use only when the visual cues matter."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {"path": {
                                "type": "string",
                                "enum": list(self.reference_paths),
                            }},
                            "required": ["path"],
                            "additionalProperties": False,
                        },
                    },
                }
            )
        return schemas

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
        if self.browser_probe_calls:
            self.browser_probe_requires_recheck = True
            self.browser_probe_verified_revision = -1
            self._successful_browser_steps = []
            self._successful_browser_flows = []

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
        if name == "browser_probe" and isinstance(result, dict):
            return _compact_browser_result(result, len(encoded))
        if name == "read_files" and isinstance(result, dict) and isinstance(result.get("files"), list):
            return json.dumps(
                {
                    "ok": bool(result.get("ok")),
                    "truncated": True,
                    "original_chars": len(encoded),
                    "re_read_files_individually": True,
                    "message": (
                        "Combined batch source exceeded the tool result limit. "
                        "No file content is supplied; read each relevant path with read_file."
                    ),
                    "files": [
                        {
                            "path": entry.get("path"),
                            "sha256": entry.get("sha256"),
                            "total_lines": entry.get("total_lines"),
                            "content_truncated": True,
                            "requested_range_complete": False,
                            "next_start_line": 1,
                        }
                        for entry in result["files"]
                        if isinstance(entry, dict)
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        summary = {
            "ok": bool(result.get("ok")) if isinstance(result, dict) else False,
            "truncated": True,
            "original_chars": len(encoded),
            "preview": encoded[: MAX_TOOL_RESULT_CHARS - 500],
        }
        if isinstance(result, dict):
            for key in (
                "path", "sha256", "total_lines", "start_line", "last_line",
                "next_start_line", "content_truncated", "next_start_char",
                "requested_end_line", "requested_range_complete",
                "character_page_required",
            ):
                if key in result:
                    summary[key] = result[key]
            if isinstance(result.get("files"), list):
                summary["files"] = [
                    {
                        key: entry[key]
                        for key in (
                            "path", "sha256", "total_lines", "start_line",
                            "last_line", "next_start_line", "content_truncated",
                            "requested_end_line", "requested_range_complete",
                            "single_file_read_required", "next_start_char",
                            "character_page_required",
                        )
                        if key in entry
                    }
                    for entry in result["files"]
                    if isinstance(entry, dict)
                ]
        return json.dumps(summary, ensure_ascii=False, sort_keys=True)

    def _tool_list_files(self, arguments: dict[str, Any]) -> dict[str, Any]:
        directory = self._safe_path(str(arguments.get("directory") or "."))
        files = []
        if directory.is_file():
            files = [str(directory.relative_to(self.root))]
        elif directory.is_dir():
            for path in sorted(directory.rglob("*")):
                if not self._safe_discovered_file(path):
                    continue
                files.append(str(path.relative_to(self.root)))
                if len(files) >= 300:
                    break
        return {"ok": True, "files": files}

    def _safe_discovered_file(self, path: Path) -> bool:
        """Recheck discovered entries; a safe search root does not make links safe."""

        if path.is_symlink():
            return False
        try:
            relative = str(path.relative_to(self.root))
            resolved = self._safe_path(relative)
        except (OSError, ValueError):
            return False
        return resolved == path and resolved.is_file()

    def _tool_read_file(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = self._safe_path(str(arguments["path"]))
        file_size = path.stat().st_size
        if file_size > MAX_READ_FILE_BYTES:
            raise ValueError(
                f"file exceeds {MAX_READ_FILE_BYTES} byte read safety limit"
            )
        source = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        relative = str(path.relative_to(self.root))
        if "start_char" in arguments:
            if "start_line" in arguments or "end_line" in arguments:
                raise ValueError("start_char cannot be combined with line cursors")
            start_char = int(arguments["start_char"])
            if not 0 <= start_char <= len(source):
                raise ValueError("start_char is outside the file")
            end_char = min(len(source), start_char + 8_000)
            while True:
                result = {
                    "ok": True,
                    "path": relative,
                    "content": source[start_char:end_char],
                    "sha256": digest,
                    "start_char": start_char,
                    "next_start_char": end_char if end_char < len(source) else None,
                    "total_chars": len(source),
                    "content_truncated": end_char < len(source),
                    "requested_range_complete": end_char == len(source),
                }
                if len(json.dumps(result, ensure_ascii=False, sort_keys=True)) <= MAX_DIRECT_READ_RESULT_CHARS:
                    return result
                end_char = start_char + max(1, (end_char - start_char) // 2)
        start = max(1, int(arguments.get("start_line") or 1))
        requested_end = int(arguments.get("end_line") or (start + 399))
        if requested_end < start:
            raise ValueError("end_line must be at least start_line")
        end = min(requested_end, start + 399)
        lines = source.splitlines()
        last_line = min(end, len(lines)) if start <= len(lines) else None
        selected = [
            f"{index}: {lines[index - 1]}"
            for index in range(start, (last_line or start - 1) + 1)
        ]
        def page(count: int) -> dict[str, Any]:
            shown_line = start + count - 1 if count else None
            next_line = (
                start + count if start + count <= len(lines) else None
            )
            return {
                "ok": True,
                "path": relative,
                "content": "\n".join(selected[:count]),
                "sha256": digest,
                "total_lines": len(lines),
                "start_line": start,
                "last_line": shown_line,
                "requested_end_line": requested_end,
                "requested_range_complete": (
                    start > len(lines)
                    or (shown_line is not None and shown_line >= min(requested_end, len(lines)))
                ),
                "next_start_line": next_line,
                "content_truncated": next_line is not None,
            }

        low, high = 0, len(selected)
        best = page(0)
        while low <= high:
            middle = (low + high) // 2
            candidate = page(middle)
            if len(json.dumps(candidate, ensure_ascii=False, sort_keys=True)) <= MAX_DIRECT_READ_RESULT_CHARS:
                best = candidate
                low = middle + 1
            else:
                high = middle - 1
        if selected and best["last_line"] is None:
            line_start = sum(
                len(line) for line in source.splitlines(keepends=True)[:start - 1]
            )
            best["character_page_required"] = True
            best["next_start_char"] = line_start
        return best

    def _tool_read_requirement_spec(self, arguments: dict[str, Any]) -> dict[str, Any]:
        req_id = str(arguments["requirement_id"])
        if req_id not in self.requirement_specs:
            raise ValueError("requirement is not assigned or is not abbreviated")
        start = int(arguments["start_char"])
        current = self.requirement_spec_offsets[req_id]
        document = self.requirement_specs[req_id]
        review = current >= len(document)
        if review:
            if not 0 <= start < len(document):
                raise ValueError("review page start must be inside the specification")
        elif start != current:
            raise ValueError(f"read requirement {req_id} sequentially from character {current}")
        end = min(len(document), start + MAX_REQUIREMENT_PAGE_CHARS)
        digest = hashlib.sha256(document.encode("utf-8")).hexdigest()
        while True:
            result = {
                "ok": True,
                "requirement_id": req_id,
                "start_char": start,
                "next_start_char": end,
                "total_chars": len(document),
                "complete": end == len(document),
                "review": review,
                "sha256": digest,
                "content": document[start:end],
            }
            if len(json.dumps(result, ensure_ascii=False, sort_keys=True)) <= MAX_TOOL_RESULT_CHARS:
                break
            end = start + max(1, (end - start) // 2)
        if not review:
            self.requirement_spec_offsets[req_id] = end
        return result

    def _tool_read_files(self, arguments: dict[str, Any]) -> dict[str, Any]:
        requested = arguments.get("paths")
        if (
            not isinstance(requested, list)
            or not 1 <= len(requested) <= MAX_BATCH_READ_FILES
        ):
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

        files = [self._tool_read_file({"path": path}) for path in normalized]
        content_budgets = _batch_content_budgets(
            [len(str(file_result.get("content") or "")) for file_result in files],
            MAX_BATCH_RESULT_CONTENT_CHARS,
        )
        for file_result, per_file_characters in zip(files, content_budgets):
            content = str(file_result.get("content") or "")
            if len(content) > per_file_characters:
                kept: list[str] = []
                used = 0
                for line in content.split("\n"):
                    cost = len(line) + (1 if kept else 0)
                    if used + cost > per_file_characters:
                        break
                    kept.append(line)
                    used += cost
                file_result["content"] = "\n".join(kept)
                file_result["content_truncated"] = True
                file_result["requested_range_complete"] = False
                file_result["last_line"] = (
                    file_result["start_line"] + len(kept) - 1 if kept else None
                )
                file_result["next_start_line"] = (
                    file_result["last_line"] + 1
                    if kept else file_result["start_line"]
                )
                if not kept:
                    file_result["single_file_read_required"] = True
        return {
            "ok": True,
            "files": files,
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
            if not self._safe_discovered_file(path):
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
                    matches.append(
                        {
                            "path": str(path.relative_to(self.root)),
                            "line": index,
                            "text": line[:300],
                        }
                    )
                    if len(matches) >= 80:
                        return {"ok": True, "matches": matches, "truncated": True}
        return {"ok": True, "matches": matches, "truncated": False}

    def _tool_inspect_reference(self, arguments: dict[str, Any]) -> dict[str, Any]:
        relative = str(arguments.get("path") or "")
        if self.visual_client is None or relative not in self.reference_paths:
            raise ValueError("reference image is not available to this batch")
        return {"ok": True, **self.visual_client.describe(relative)}

    def _tool_write_file(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self._require_complete_specs()
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
                raise ValueError(
                    "file changed since read_file; SHA-256 precondition failed"
                )
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
        self._require_complete_specs()
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
            results = run_quick_checks(self.root)
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

    def _tool_browser_probe(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.maximum_browser_probe_calls:
            raise ValueError("browser probe is disabled")
        if self.browser_probe_calls >= self.maximum_browser_probe_calls:
            raise ValueError("browser probe call budget exhausted for this batch")
        if not self.current_changes_validated:
            raise ValueError("run passing quick validation for the current revision first")
        try:
            steps = validate_steps(arguments.get("steps"))
        except ValueError:
            # A rejected plan performed no behavioral verification. Keep an
            # outstanding obligation, without charging a browser launch.
            if self.browser_probe_verified_revision != self.change_revision:
                self.browser_probe_requires_recheck = True
                self._successful_browser_steps = []
            raise
        previously_verified = (
            not self.browser_probe_requires_recheck
            and self.browser_probe_verified_revision == self.change_revision
        )
        previous_steps = self.verified_browser_steps
        previous_flows = self.verified_browser_flows
        self.browser_probe_calls += 1
        self.browser_probe_requires_recheck = True
        self.browser_probe_verified_revision = -1
        self._successful_browser_steps = []
        self._successful_browser_flows = []
        result = probe_local_app(self.root, self.smoke_port, steps)
        if (
            result.get("ok")
            and (
                previously_verified
                or (result.get("behavioral_checks", 0) > 0 and result.get("behavioral_assertions", 0) > 0)
            )
        ):
            self.browser_probe_requires_recheck = False
            self.browser_probe_verified_revision = self.change_revision
            self._successful_browser_steps = (
                steps if result.get("behavioral_checks", 0) > 0
                and result.get("behavioral_assertions", 0) > 0 else previous_steps
            )
            self._successful_browser_flows = previous_flows
            if self._successful_browser_steps not in self._successful_browser_flows:
                self._successful_browser_flows.append(self._successful_browser_steps)
        return result
