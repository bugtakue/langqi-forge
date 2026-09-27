"""Output-directory file operations: listing, context selection and applying model file blocks."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

PROTECTED = {"backend/server.js", "backend/lib/db.js", "frontend/src/lib/core.js", "frontend/build.js",
             "frontend/package.json", "backend/package.json"}
ALLOWED_PREFIXES = ("frontend/src/", "backend/routes/", "backend/seed/", "backend/lib/")
SKIP_DIRS = {"node_modules", "dist", "data", ".git"}

FILE_RE = re.compile(r"<<<FILE:\s*(?P<path>[^>\n]+?)\s*>>>\n(?P<body>.*?)\n?<<<END FILE>>>", re.S)
EDIT_RE = re.compile(r"<<<EDIT:\s*(?P<path>[^>\n]+?)\s*>>>\s*\n(?P<body>.*?)<<<END EDIT>>>", re.S)
SR_RE = re.compile(r"<<<SEARCH>>>\n(?P<search>.*?)\n?<<<REPLACE>>>\n?(?P<replace>.*?)(?=\n?<<<SEARCH>>>|\Z)", re.S)


class Workspace:
    def __init__(self, root: Path, extra_allowed: tuple[str, ...] = ()) -> None:
        self.root = Path(root).resolve()
        self.extra_allowed = extra_allowed

    def path(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if not str(p).startswith(str(self.root)):
            raise ValueError(f"path escapes workspace: {rel}")
        return p

    def read(self, rel: str) -> str:
        p = self.path(rel)
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def write(self, rel: str, content: str) -> None:
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def app_files(self) -> list[str]:
        out = []
        for base in ("frontend", "backend"):
            root = self.root / base
            if not root.exists():
                continue
            for p in sorted(root.rglob("*")):
                if p.is_file() and not any(part in SKIP_DIRS for part in p.relative_to(self.root).parts):
                    out.append(str(p.relative_to(self.root)))
        return out

    def editable_files(self) -> list[str]:
        return [f for f in self.app_files() if f not in PROTECTED and f.startswith(ALLOWED_PREFIXES)]

    def snapshot(self) -> dict[str, str]:
        return {f: self.read(f) for f in self.editable_files()}

    def restore(self, snap: dict[str, str]) -> None:
        for f in self.editable_files():
            if f not in snap:
                self.path(f).unlink(missing_ok=True)
        for f, content in snap.items():
            self.write(f, content)

    def allowed(self, rel: str) -> bool:
        rel = rel.strip().lstrip("./")
        if rel in PROTECTED:
            return False
        return rel.startswith(ALLOWED_PREFIXES) or rel.startswith(self.extra_allowed)

    def apply(self, text: str) -> tuple[list[str], list[str]]:
        """Apply FILE and EDIT blocks. Returns (changed_paths, error_messages)."""
        changed: list[str] = []
        errors: list[str] = []
        for m in FILE_RE.finditer(text):
            rel = m.group("path").strip().strip("`").lstrip("./")
            if not self.allowed(rel):
                errors.append(f"refused to write protected/unknown path {rel}")
                continue
            body = m.group("body")
            body = strip_fence(body)
            self.write(rel, body.rstrip() + "\n")
            changed.append(rel)
        for m in EDIT_RE.finditer(text):
            rel = m.group("path").strip().strip("`").lstrip("./")
            if not self.allowed(rel):
                errors.append(f"refused to edit protected/unknown path {rel}")
                continue
            current = self.read(rel)
            if not current and not self.path(rel).exists():
                errors.append(f"EDIT target does not exist: {rel} (use FILE to create it)")
                continue
            ok_any = False
            for sr in SR_RE.finditer(m.group("body")):
                search, replace = sr.group("search"), sr.group("replace")
                replace = re.sub(r"\n?$", "", replace, count=1) if replace.endswith("\n") else replace
                new = apply_search_replace(current, search, replace)
                if new is None:
                    errors.append(f"EDIT search text not found in {rel}: {search[:160]!r}")
                    continue
                current = new
                ok_any = True
            if ok_any:
                self.write(rel, current)
                changed.append(rel)
        return list(dict.fromkeys(changed)), errors

    def context_files(self, priority: list[str], budget_chars: int = 90000) -> tuple[str, list[str]]:
        """Render full content of files in priority order within a budget; returns (text, omitted_files)."""
        files = self.editable_files()
        ordered = [f for f in dict.fromkeys(priority) if f in files] + [f for f in files if f not in priority]
        shown, omitted, used = [], [], 0
        for f in ordered:
            content = self.read(f)
            block = f"<<<FILE: {f}>>>\n{content}\n<<<END FILE>>>\n"
            if f in priority and used + len(block) <= budget_chars:
                shown.append(block)
                used += len(block)
            elif f not in priority and used + len(block) <= budget_chars * 0.5:
                shown.append(block)
                used += len(block)
            else:
                omitted.append(f"{f} ({len(content)} chars)")
        return "\n".join(shown) or "(none yet)", omitted


def strip_fence(body: str) -> str:
    lines = body.split("\n")
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
    return "\n".join(lines)


def apply_search_replace(current: str, search: str, replace: str) -> str | None:
    if search and current.count(search) >= 1:
        return current.replace(search, replace, 1)
    # tolerant match: ignore trailing whitespace differences line by line
    s_lines = [l.rstrip() for l in search.strip("\n").split("\n")]
    c_lines = current.split("\n")
    n = len(s_lines)
    if n == 0:
        return None
    for i in range(len(c_lines) - n + 1):
        if [l.rstrip() for l in c_lines[i:i + n]] == s_lines:
            return "\n".join(c_lines[:i] + replace.split("\n") + c_lines[i + n:])
    # indentation-insensitive match
    s_strip = [l.strip() for l in s_lines]
    for i in range(len(c_lines) - n + 1):
        if [l.strip() for l in c_lines[i:i + n]] == s_strip:
            return "\n".join(c_lines[:i] + replace.split("\n") + c_lines[i + n:])
    return None


def copy_scaffold(scaffold: Path, out: Path) -> None:
    for sub in ("frontend", "backend"):
        src = scaffold / sub
        dst = out / sub
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    (out / "frontend" / "src" / "pages").mkdir(parents=True, exist_ok=True)
    (out / "backend" / "routes").mkdir(parents=True, exist_ok=True)
    (out / "backend" / "seed").mkdir(parents=True, exist_ok=True)
