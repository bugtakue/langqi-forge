from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .checks import frontend_build_check, run_full_checks, structure_check
from .trace import ProductionTrace


EXCLUDED_PARTS = {".git", "node_modules", "dist", "coverage", "__pycache__"}
WRITABLE_ROOTS = {"frontend", "backend"}


class WorkspaceTools:
    def __init__(self, root: Path, trace: ProductionTrace, smoke_port: int) -> None:
        self.root = root.resolve()
        self.trace = trace
        self.smoke_port = smoke_port
        self.changed_files: set[str] = set()

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
                        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
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
        resolved = (self.root / candidate).resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise ValueError("path escapes the project")
        relative_parts = resolved.relative_to(self.root).parts
        if any(part in EXCLUDED_PARTS for part in relative_parts):
            raise ValueError("generated or control directories are not accessible")
        if writable and (not relative_parts or relative_parts[0] not in WRITABLE_ROOTS):
            raise ValueError("writes are limited to frontend/ and backend/")
        return resolved

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
        encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)
        self.trace.record("tool_result", tool=name, result=result)
        return encoded[:12000]

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
                if any(part in EXCLUDED_PARTS for part in relative.parts):
                    continue
                files.append(str(relative))
                if len(files) >= 300:
                    break
        return {"ok": True, "files": files}

    def _tool_read_file(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = self._safe_path(str(arguments["path"]))
        start = max(1, int(arguments.get("start_line") or 1))
        requested_end = int(arguments.get("end_line") or (start + 399))
        end = min(requested_end, start + 399)
        lines = path.read_text(encoding="utf-8").splitlines()
        selected = [f"{index}: {lines[index - 1]}" for index in range(start, min(end, len(lines)) + 1)]
        return {"ok": True, "path": str(path.relative_to(self.root)), "content": "\n".join(selected)}

    def _tool_search_text(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments["query"])
        if len(query) > 200:
            raise ValueError("query too long")
        matcher = re.compile(re.escape(query), re.IGNORECASE)
        directory = self._safe_path(str(arguments.get("directory") or "."))
        matches: list[dict[str, Any]] = []
        paths = [directory] if directory.is_file() else sorted(directory.rglob("*"))
        for path in paths:
            if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.relative_to(self.root).parts):
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
        if len(content.encode("utf-8")) > 750_000:
            raise ValueError("file content exceeds 750KB")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        relative = str(path.relative_to(self.root))
        self.changed_files.add(relative)
        return {"ok": True, "path": relative, "bytes": len(content.encode("utf-8"))}

    def _tool_replace_text(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = self._safe_path(str(arguments["path"]), writable=True)
        old = str(arguments["old"])
        new = str(arguments["new"])
        expected_count = int(arguments.get("expected_count") or 1)
        content = path.read_text(encoding="utf-8")
        count = content.count(old)
        if count != expected_count:
            raise ValueError(f"expected {expected_count} occurrence(s), found {count}")
        path.write_text(content.replace(old, new), encoding="utf-8")
        relative = str(path.relative_to(self.root))
        self.changed_files.add(relative)
        return {"ok": True, "path": relative, "replacements": count}

    def _tool_run_validation(self, arguments: dict[str, Any]) -> dict[str, Any]:
        scope = str(arguments["scope"])
        if scope == "structure":
            results = [structure_check(self.root)]
        elif scope == "quick":
            results = [structure_check(self.root)]
            if results[-1].passed:
                results.append(frontend_build_check(self.root))
        elif scope == "full":
            results = run_full_checks(self.root, self.smoke_port)
        else:
            raise ValueError(f"unsupported validation scope: {scope}")
        return {"ok": all(result.passed for result in results), "checks": [result.as_dict() for result in results]}
