from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .artifacts import canonical_json, read_json_object, verify_run_envelope
from .qualification import qualify
from .trace import find_unredacted_secrets, reseal_trace_rows, verify_trace_rows

RUN_FILES = {
    "github": (
        ".arc/harness-report.json",
        ".arc/planner-contract.json",
        ".arc/compiled-plan.json",
        ".arc/production-trace.jsonl",
        ".arc/run-envelope.json",
        ".arc/capability-capsule.json",
        ".arc/public-eval/github.feedback.json",
        ".arc/public-eval/github.playwright.json",
        ".arc/public-eval/github.adversarial.feedback.json",
        ".arc/public-eval/github.adversarial.playwright.json",
    ),
    "sheet": (
        ".arc/harness-report.json",
        ".arc/planner-contract.json",
        ".arc/compiled-plan.json",
        ".arc/production-trace.jsonl",
        ".arc/run-envelope.json",
        ".arc/capability-capsule.json",
        ".arc/public-eval/sheet.feedback.json",
        ".arc/public-eval/sheet.playwright.json",
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
) -> dict[str, Any]:
    rows = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    sequences = [row.get("sequence") for row in rows]
    if sequences != list(range(1, len(rows) + 1)):
        raise ValueError(f"trace sequence is not contiguous: {source}")
    verification = verify_trace_rows(rows, require_fully_sealed=True)
    if not verification["valid"]:
        raise ValueError(
            f"trace integrity failed at row {verification.get('row')}: {source}"
        )
    secret_findings = find_unredacted_secrets(rows)
    if secret_findings:
        first = secret_findings[0]
        raise ValueError(
            "trace contains unredacted secret material at "
            f"{first['path']} ({first['reason']})"
        )
    source_sha256 = _sha256(source)
    source_head = verification["head"]
    rows = reseal_trace_rows([_sanitize(row, replacements) for row in rows])
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendered = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
        for row in rows
    )
    destination.write_text(rendered, encoding="utf-8")
    sanitized_verification = verify_trace_rows(rows, require_fully_sealed=True)
    return {
        "rows": len(rows),
        "transformation": "deterministic-path-redaction-and-reseal-v2",
        "source_sha256": source_sha256,
        "source_head": source_head,
        "sanitized_sha256": _sha256(destination),
        "sanitized_head": sanitized_verification["head"],
    }


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
    for project in projects.values():
        if (
            output_dir == project
            or output_dir in project.parents
            or project in output_dir.parents
        ):
            raise ValueError("evidence output must be disjoint from generated projects")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("evidence output directory must be new or empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_files = []
    trace_exports: dict[str, dict[str, Any]] = {}
    qualification_payload = read_json_object(qualification)
    if qualification_payload.get("passed") is not True:
        raise ValueError("cannot export a failed qualification report")
    model_policy = qualification_payload.get("model_policy") or {}
    thresholds = qualification_payload.get("thresholds") or {}
    allowed_models_value = model_policy.get("allowed_models")
    allowed_models = (
        tuple(str(item) for item in allowed_models_value)
        if isinstance(allowed_models_value, list) and allowed_models_value
        else None
    )
    recomputed = qualify(
        projects["github"],
        projects["sheet"],
        github_max_seconds=float(thresholds.get("github_max_seconds") or 20.0),
        sheet_max_seconds=float(thresholds.get("sheet_max_seconds") or 30.0),
        allowed_models=allowed_models,
        expected_gateway_host=model_policy.get("required_gateway_host"),
        expected_gateway_provenance=model_policy.get(
            "required_gateway_provenance"
        ),
    )
    if recomputed.get("passed") is not True or canonical_json(
        recomputed.get("evidence")
    ) != canonical_json(qualification_payload.get("evidence")):
        raise ValueError("qualification report cannot be reproduced from the projects")
    qualification_evidence = qualification_payload.get("evidence") or {}
    qualified_files = {
        "github_generation": projects["github"] / ".arc" / "harness-report.json",
        "sheet_generation": projects["sheet"] / ".arc" / "harness-report.json",
        "github_baseline": projects["github"]
        / ".arc"
        / "public-eval"
        / "github.feedback.json",
        "github_adversarial": projects["github"]
        / ".arc"
        / "public-eval"
        / "github.adversarial.feedback.json",
        "sheet_baseline": projects["sheet"]
        / ".arc"
        / "public-eval"
        / "sheet.feedback.json",
    }
    if set(qualification_evidence) != set(qualified_files):
        raise ValueError("qualification report has an unexpected evidence set")
    for label, source in qualified_files.items():
        item = qualification_evidence.get(label)
        checks = item.get("checks") if isinstance(item, dict) else None
        if (
            not isinstance(item, dict)
            or item.get("passed") is not True
            or not isinstance(checks, list)
            or not checks
            or not all(
                isinstance(check, dict) and check.get("passed") is True
                for check in checks
            )
            or item.get("sha256") != _sha256(source)
        ):
            raise ValueError(f"qualification evidence is not bound and green: {label}")
    for project in projects.values():
        verify_run_envelope(project)

    for name, project in projects.items():
        for relative in RUN_FILES[name]:
            source = project / relative
            if not source.is_file():
                raise FileNotFoundError(f"missing evidence file: {source}")
            destination = output_dir / name / Path(relative).name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            manifest_files.append(
                {
                    "path": str(destination.relative_to(output_dir)),
                    "sha256": _sha256(destination),
                    "bytes": destination.stat().st_size,
                }
            )
            if source.name == "production-trace.jsonl":
                sanitized_destination = (
                    output_dir / name / "production-trace.sanitized.jsonl"
                )
                replacements = tuple(
                    sorted(
                        (
                            (str(project), f"<{name}-generated-project>"),
                            (
                                str(Path.cwd().resolve()),
                                "<harness-repository>",
                            ),
                        ),
                        key=lambda pair: len(pair[0]),
                        reverse=True,
                    )
                )
                trace_exports[name] = _export_trace(
                    source, sanitized_destination, replacements
                )
                manifest_files.append(
                    {
                        "path": str(sanitized_destination.relative_to(output_dir)),
                        "sha256": _sha256(sanitized_destination),
                        "bytes": sanitized_destination.stat().st_size,
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
        "version": 2,
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": (
            "exact source-bound production evidence plus a separately resealed, "
            "path-sanitized trace; public task source is intentionally excluded"
        ),
        "trace_exports": trace_exports,
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
