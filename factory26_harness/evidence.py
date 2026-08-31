from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RUN_FILES = {
    "github": (
        ".arc/harness-report.json",
        ".arc/planner-contract.json",
        ".arc/compiled-plan.json",
        ".arc/production-trace.jsonl",
        ".arc/public-eval/github.feedback.json",
        ".arc/public-eval/github.adversarial.feedback.json",
    ),
    "sheet": (
        ".arc/harness-report.json",
        ".arc/planner-contract.json",
        ".arc/compiled-plan.json",
        ".arc/production-trace.jsonl",
        ".arc/public-eval/sheet.feedback.json",
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sanitize(value: Any, replacements: tuple[tuple[str, str], ...]) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize(child, replacements) for key, child in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(child, replacements) for child in value]
    if isinstance(value, str):
        sanitized = value
        for original, replacement in replacements:
            sanitized = sanitized.replace(original, replacement)
        return sanitized
    return value


def _export_trace(
    source: Path, destination: Path, replacements: tuple[tuple[str, str], ...]
) -> int:
    rows = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(_sanitize(json.loads(line), replacements))
    sequences = [row.get("sequence") for row in rows]
    if sequences != list(range(1, len(rows) + 1)):
        raise ValueError(f"trace sequence is not contiguous: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendered = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
        for row in rows
    )
    destination.write_text(rendered, encoding="utf-8")
    return len(rows)


def export_evidence(
    github_project: Path,
    sheet_project: Path,
    qualification: Path,
    output_dir: Path,
) -> dict[str, Any]:
    projects = {
        "github": github_project.resolve(),
        "sheet": sheet_project.resolve(),
    }
    qualification = qualification.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_files = []
    trace_events: dict[str, int] = {}
    replacements = tuple(
        sorted(
            (
                (str(project), f"<{name}-generated-project>")
                for name, project in projects.items()
            ),
            key=lambda pair: len(pair[0]),
            reverse=True,
        )
    ) + ((str(Path.cwd().resolve()), "<harness-repository>"),)

    for name, project in projects.items():
        for relative in RUN_FILES[name]:
            source = project / relative
            if not source.is_file():
                raise FileNotFoundError(f"missing evidence file: {source}")
            destination = output_dir / name / Path(relative).name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.name == "production-trace.jsonl":
                trace_events[name] = _export_trace(source, destination, replacements)
            else:
                shutil.copyfile(source, destination)
            manifest_files.append(
                {
                    "path": str(destination.relative_to(output_dir)),
                    "sha256": _sha256(destination),
                    "bytes": destination.stat().st_size,
                }
            )

    qualification_destination = output_dir / "qualification.json"
    shutil.copyfile(qualification, qualification_destination)
    manifest_files.append(
        {
            "path": qualification_destination.name,
            "sha256": _sha256(qualification_destination),
            "bytes": qualification_destination.stat().st_size,
        }
    )
    manifest = {
        "version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": "sanitized public production trajectory; public task source is intentionally excluded",
        "trace_events": trace_events,
        "files": sorted(manifest_files, key=lambda item: item["path"]),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export sanitized Factory26 production evidence"
    )
    parser.add_argument("--github-project", type=Path, required=True)
    parser.add_argument("--sheet-project", type=Path, required=True)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = export_evidence(
        args.github_project,
        args.sheet_project,
        args.qualification,
        args.output_dir,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
