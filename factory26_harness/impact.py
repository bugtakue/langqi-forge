from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


class ChangeImpactGraph:
    """Observed requirement-to-file links; never guesses hidden test coverage."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.requirements: dict[str, set[str]] = {}
        self.checks: dict[str, set[str]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for req_id, files in (payload.get("requirements") or {}).items():
            self.requirements[str(req_id)] = {str(path) for path in files}
        for check, files in (payload.get("checks") or {}).items():
            self.checks[str(check)] = {str(path) for path in files}

    def record_requirement_files(self, requirement_ids: Iterable[str], files: Iterable[str]) -> None:
        normalized_files = {str(path).strip() for path in files if str(path).strip()}
        for req_id in requirement_ids:
            normalized_id = str(req_id).strip()
            if normalized_id:
                self.requirements.setdefault(normalized_id, set()).update(normalized_files)
        self.save()

    def record_check_files(self, check_name: str, files: Iterable[str]) -> None:
        normalized = str(check_name).strip()
        if normalized:
            self.checks.setdefault(normalized, set()).update(
                str(path).strip() for path in files if str(path).strip()
            )
            self.save()

    def files_for_requirements(self, requirement_ids: Iterable[str]) -> list[str]:
        files: set[str] = set()
        for req_id in requirement_ids:
            files.update(self.requirements.get(str(req_id), set()))
        return sorted(files)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "policy": "observed-links-only; final-full-check-required",
            "requirements": {key: sorted(value) for key, value in sorted(self.requirements.items())},
            "checks": {key: sorted(value) for key, value in sorted(self.checks.items())},
        }
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
