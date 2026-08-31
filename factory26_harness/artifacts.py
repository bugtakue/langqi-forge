from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


ENVELOPE_VERSION = 2
_SOURCE_ROOTS = ("frontend", "backend")
_SOURCE_EXCLUDED_PARTS = frozenset({"node_modules", "dist", "data", ".git", "__pycache__"})


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(canonical_json(value) + b"\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _tree_manifest(root: Path, files: list[Path]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"artifact tree contains a non-regular file: {path}")
        relative = path.relative_to(root).as_posix()
        content = path.read_bytes()
        entries.append(
            {
                "path": relative,
                "bytes": len(content),
                "sha256": sha256_bytes(content),
            }
        )
    return {
        "algorithm": "sha256-canonical-file-list-v1",
        "sha256": sha256_bytes(canonical_json(entries)),
        "file_count": len(entries),
        "files": entries,
    }


def application_source_manifest(project_dir: Path) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    files: list[Path] = []
    for root_name in _SOURCE_ROOTS:
        root = project_dir / root_name
        if not root.is_dir():
            raise FileNotFoundError(f"generated application is missing {root_name}/")
        for path in root.rglob("*"):
            relative = path.relative_to(project_dir)
            if any(part in _SOURCE_EXCLUDED_PARTS for part in relative.parts):
                continue
            if path.is_file() or path.is_symlink():
                files.append(path)
    if not files:
        raise ValueError("generated application source tree is empty")
    return _tree_manifest(project_dir, files)


def test_bundle_manifest(tests_dir: Path) -> dict[str, Any]:
    tests_dir = tests_dir.resolve()
    if not tests_dir.is_dir():
        raise FileNotFoundError(f"test bundle is missing: {tests_dir}")
    files = [
        path
        for path in tests_dir.rglob("*")
        if path.is_file() or path.is_symlink()
    ]
    if not files:
        raise ValueError("test bundle is empty")
    return _tree_manifest(tests_dir, files)


def public_task_bundle_manifest(task_root: Path) -> dict[str, Any]:
    task_root = task_root.resolve()
    manifest_path = task_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"public task manifest is missing: {manifest_path}")
    payload = read_json_object(manifest_path)
    declared = payload.get("test_files")
    if not isinstance(declared, dict) or not declared:
        raise ValueError("public task manifest has no locked test files")
    tests_dir = task_root / "tests"
    test_manifest = test_bundle_manifest(tests_dir)
    observed = {
        entry["path"]: entry["sha256"] for entry in test_manifest["files"]
    }
    normalized_declared = {
        str(path): str(digest) for path, digest in declared.items()
    }
    if observed != normalized_declared:
        raise ValueError("public test bundle does not match its synchronized manifest")
    return {
        "task_id": payload.get("task_id"),
        "requirements_sha256": payload.get("requirements_sha256"),
        "expected_test_count": payload.get("expected_test_count"),
        "task_manifest_sha256": sha256_file(manifest_path),
        "tests": test_manifest,
    }


def trace_rows(path: Path, *, require_fully_sealed: bool = True) -> list[dict[str, Any]]:
    from .trace import verify_trace_rows

    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    verification = verify_trace_rows(rows, require_fully_sealed=require_fully_sealed)
    if not verification["valid"]:
        raise ValueError(
            f"trace integrity failed at row {verification.get('row')}: {verification.get('reason')}"
        )
    return rows


def _event_rows(rows: list[dict[str, Any]], event: str) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("event") == event]


def build_run_envelope(project_dir: Path) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    arc = project_dir / ".arc"
    report_path = arc / "harness-report.json"
    planner_path = arc / "planner-contract.json"
    plan_path = arc / "compiled-plan.json"
    trace_path = arc / "production-trace.jsonl"
    for path in (report_path, planner_path, plan_path, trace_path):
        if not path.is_file():
            raise FileNotFoundError(f"run envelope input is missing: {path}")

    report = read_json_object(report_path)
    planner = read_json_object(planner_path)
    plan = read_json_object(plan_path)
    run_id = str(report.get("run_id") or "")
    if not run_id:
        raise ValueError("harness report has no run id")
    if planner.get("run_id") != run_id or plan.get("run_id") != run_id:
        raise ValueError("planner artifacts are not bound to the harness run id")
    rows = trace_rows(trace_path)
    requests = _event_rows(rows, "model_request")
    responses = _event_rows(rows, "model_response")
    tool_calls = _event_rows(rows, "agent_tool_call")
    completions = _event_rows(rows, "run_completed")
    source = application_source_manifest(project_dir)
    if report.get("application_source") != source:
        raise ValueError("harness report is not bound to the current application source")

    if len(completions) != 1:
        raise ValueError("run envelope requires exactly one run_completed event")
    completed_report = (completions[0].get("payload") or {}).get("report")
    if canonical_json(completed_report) != canonical_json(report):
        raise ValueError("run_completed report does not match harness-report.json")

    evaluations: list[dict[str, Any]] = []
    public_root = arc / "public-eval"
    if public_root.is_dir():
        for feedback_path in sorted(public_root.glob("*.feedback.json")):
            feedback = read_json_object(feedback_path)
            label = str(feedback.get("run_label") or "")
            playwright_path = public_root / f"{label}.playwright.json"
            if not label or not playwright_path.is_file():
                raise ValueError(f"public evaluation is missing its raw Playwright report: {feedback_path}")
            feedback_sha256 = sha256_file(feedback_path)
            playwright_sha256 = sha256_file(playwright_path)
            if feedback.get("playwright_report_sha256") != playwright_sha256:
                raise ValueError(f"public evaluation raw report hash mismatch: {feedback_path}")
            if feedback.get("application_source_sha256") != source["sha256"]:
                raise ValueError(f"public evaluation source hash mismatch: {feedback_path}")
            evaluations.append(
                {
                    "run_label": label,
                    "feedback_path": feedback_path.relative_to(project_dir).as_posix(),
                    "feedback_sha256": feedback_sha256,
                    "playwright_path": playwright_path.relative_to(project_dir).as_posix(),
                    "playwright_sha256": playwright_sha256,
                    "application_source_sha256": feedback.get("application_source_sha256"),
                    "test_bundle_sha256": feedback.get("test_bundle_sha256"),
                }
            )

    completed_evaluations = _event_rows(rows, "public_evaluation_completed")
    completed_by_label = {
        str((row.get("payload") or {}).get("run_label") or ""): row
        for row in completed_evaluations
    }
    if len(completed_by_label) != len(completed_evaluations):
        raise ValueError("public evaluation trace contains a duplicate run label")
    if set(completed_by_label) != {item["run_label"] for item in evaluations}:
        raise ValueError("public evaluation files and completed trace events differ")
    for evaluation in evaluations:
        event = completed_by_label[evaluation["run_label"]].get("payload") or {}
        if (
            event.get("evidence_sha256") != evaluation["feedback_sha256"]
            or event.get("playwright_report_sha256")
            != evaluation["playwright_sha256"]
            or event.get("application_source_sha256")
            != evaluation["application_source_sha256"]
            or event.get("test_bundle_sha256")
            != evaluation["test_bundle_sha256"]
        ):
            raise ValueError(
                f"public evaluation trace bindings do not match {evaluation['run_label']}"
            )

    derived_artifacts: dict[str, Any] = {"counterexamples": []}
    capsule_path = arc / "capability-capsule.json"
    capsule_events = _event_rows(rows, "capability_capsule_forged")
    if capsule_path.is_file():
        capsule_sha256 = sha256_file(capsule_path)
        if (
            len(capsule_events) != 1
            or (capsule_events[0].get("payload") or {}).get("capsule_sha256")
            != capsule_sha256
        ):
            raise ValueError("capability capsule is not bound to exactly one trace event")
        capsule = read_json_object(capsule_path)
        derived_artifacts["capability_capsule"] = {
            "path": ".arc/capability-capsule.json",
            "sha256": capsule_sha256,
            "capsule_id": capsule.get("capsule_id"),
        }
    elif capsule_events:
        raise ValueError("capability capsule trace event has no capsule file")

    counterexample_events = {
        str((row.get("payload") or {}).get("run_label") or ""): row
        for row in _event_rows(rows, "counterexample_observed")
    }
    counterexample_root = arc / "counterexamples"
    if counterexample_root.is_dir():
        for counterexample_path in sorted(counterexample_root.glob("*.json")):
            payload = read_json_object(counterexample_path)
            label = str(payload.get("run_label") or "")
            digest = sha256_file(counterexample_path)
            event = counterexample_events.get(label)
            if not label or event is None or (event.get("payload") or {}).get(
                "counterexample_sha256"
            ) != digest:
                raise ValueError(
                    f"counterexample is not bound to its trace event: {counterexample_path}"
                )
            derived_artifacts["counterexamples"].append(
                {
                    "run_label": label,
                    "path": counterexample_path.relative_to(project_dir).as_posix(),
                    "sha256": digest,
                }
            )
    if set(counterexample_events) != {
        item["run_label"] for item in derived_artifacts["counterexamples"]
    }:
        raise ValueError("counterexample files and trace events differ")
    return {
        "version": ENVELOPE_VERSION,
        "run_id": run_id,
        "requirement_sha256": report.get("requirement_sha256"),
        "application_source": source,
        "bound_files": {
            "harness_report": {
                "path": ".arc/harness-report.json",
                "sha256": sha256_file(report_path),
            },
            "planner_contract": {
                "path": ".arc/planner-contract.json",
                "sha256": sha256_file(planner_path),
            },
            "compiled_plan": {
                "path": ".arc/compiled-plan.json",
                "sha256": sha256_file(plan_path),
            },
        },
        "model_events": {
            "request_hashes": [row.get("hash") for row in requests],
            "response_hashes": [row.get("hash") for row in responses],
            "tool_call_hashes": [row.get("hash") for row in tool_calls],
        },
        "run_completed_hashes": [row.get("hash") for row in completions],
        "trace": {
            "path": ".arc/production-trace.jsonl",
            "sha256": sha256_file(trace_path),
            "rows": len(rows),
            "head": rows[-1].get("hash") if rows else "GENESIS",
            "fully_sealed": all(row.get("trace_version") == 2 for row in rows),
        },
        "evaluations": evaluations,
        "derived_artifacts": derived_artifacts,
    }


def write_run_envelope(project_dir: Path) -> dict[str, Any]:
    envelope = build_run_envelope(project_dir)
    atomic_write_json(Path(project_dir) / ".arc" / "run-envelope.json", envelope)
    return envelope


def verify_run_envelope(project_dir: Path) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    path = project_dir / ".arc" / "run-envelope.json"
    if not path.is_file():
        raise FileNotFoundError(f"run envelope is missing: {path}")
    recorded = read_json_object(path)
    expected = build_run_envelope(project_dir)
    if canonical_json(recorded) != canonical_json(expected):
        raise ValueError("run envelope does not match the current artifacts")
    return expected
