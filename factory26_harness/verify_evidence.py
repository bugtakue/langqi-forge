from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from .artifacts import canonical_json, read_json_object, sha256_file
from .capability_memory import capability_shape, verify_capability_capsule
from .evidence import RUN_FILES, _sanitize
from .qualification import (
    PUBLIC_REQUIREMENT_SHA256,
    PUBLIC_TEST_BUNDLE_SHA256,
    evaluate_generation,
    evaluate_run,
)
from .trace import find_unredacted_secrets, reseal_trace_rows, verify_trace_rows


EXPECTED_QUALIFICATION_FILES = {
    "github_generation": "github/harness-report.json",
    "sheet_generation": "sheet/harness-report.json",
    "github_baseline": "github/github.feedback.json",
    "github_adversarial": "github/github.adversarial.feedback.json",
    "sheet_baseline": "sheet/sheet.feedback.json",
}
EXPECTED_EVALUATIONS = {
    "github": {
        "github": "baseline",
        "github.adversarial": "adversarial",
    },
    "sheet": {"sheet": "baseline"},
}
EXPECTED_MANIFEST_FILES = {
    "qualification.json",
    *(
        f"{domain}/{Path(relative).name}"
        for domain, relatives in RUN_FILES.items()
        for relative in relatives
    ),
    *(f"{domain}/production-trace.sanitized.jsonl" for domain in RUN_FILES),
}


def _safe_bundle_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
        raise ValueError(f"unsafe evidence path: {relative}")
    resolved = (root / candidate).resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError(f"evidence path escapes the bundle: {relative}")
    if resolved.is_symlink() or not resolved.is_file():
        raise ValueError(f"evidence file is missing or non-regular: {relative}")
    return resolved


def _trace(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    verification = verify_trace_rows(rows, require_fully_sealed=True)
    if verification.get("valid") is not True:
        raise ValueError(
            f"trace integrity failed at row {verification.get('row')}: {path}"
        )
    findings = find_unredacted_secrets(rows)
    if findings:
        raise ValueError(
            f"trace contains unredacted secret material at {findings[0]['path']}"
        )
    return rows, verification


def _event_hashes(rows: list[dict[str, Any]], event: str) -> list[Any]:
    return [row.get("hash") for row in rows if row.get("event") == event]


def _verify_sanitized_transformation(
    *,
    domain: str,
    exact_rows: list[dict[str, Any]],
    sanitized_rows: list[dict[str, Any]],
    trace_export: dict[str, Any],
) -> None:
    if trace_export.get("transformation") != (
        "deterministic-path-redaction-and-reseal-v2"
    ):
        raise ValueError(f"{domain} trace uses an unsupported redaction transform")
    starts = [row for row in exact_rows if row.get("event") == "run_started"]
    if len(starts) != 1:
        raise ValueError(f"{domain} trace must contain one run_started event")
    payload = starts[0].get("payload") or {}
    project_root = str(payload.get("output_dir") or "")
    requirement_path = str(payload.get("requirement_path") or "")
    requirement_suffix = f"/.cache/public-tasks/{domain}/requirements"
    if (
        not project_root.startswith("/")
        or not requirement_path.startswith("/")
        or not requirement_path.endswith(requirement_suffix)
    ):
        raise ValueError(f"{domain} trace does not expose derivable absolute roots")
    repository_root = requirement_path[: -len(requirement_suffix)]
    replacements = tuple(
        sorted(
            (
                (project_root, f"<{domain}-generated-project>"),
                (repository_root, "<harness-repository>"),
            ),
            key=lambda pair: len(pair[0]),
            reverse=True,
        )
    )
    expected = reseal_trace_rows(
        [_sanitize(row, replacements) for row in exact_rows]
    )
    if canonical_json(expected) != canonical_json(sanitized_rows):
        raise ValueError(
            f"{domain} sanitized trace is not the declared exact transformation"
        )


def _verify_domain(root: Path, domain: str, trace_export: dict[str, Any]) -> dict[str, Any]:
    domain_root = root / domain
    report_path = domain_root / "harness-report.json"
    planner_path = domain_root / "planner-contract.json"
    plan_path = domain_root / "compiled-plan.json"
    envelope_path = domain_root / "run-envelope.json"
    trace_path = domain_root / "production-trace.jsonl"
    sanitized_path = domain_root / "production-trace.sanitized.jsonl"
    for path in (
        report_path,
        planner_path,
        plan_path,
        envelope_path,
        trace_path,
        sanitized_path,
    ):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"required {domain} evidence is missing: {path.name}")

    report = read_json_object(report_path)
    planner = read_json_object(planner_path)
    plan = read_json_object(plan_path)
    envelope = read_json_object(envelope_path)
    rows, exact_verification = _trace(trace_path)
    sanitized_rows, sanitized_verification = _trace(sanitized_path)
    if (
        trace_export.get("source_sha256") != sha256_file(trace_path)
        or trace_export.get("source_head") != exact_verification.get("head")
        or trace_export.get("sanitized_sha256") != sha256_file(sanitized_path)
        or trace_export.get("sanitized_head") != sanitized_verification.get("head")
        or trace_export.get("rows") != len(rows)
    ):
        raise ValueError(f"{domain} exact/sanitized trace transformation is not bound")
    _verify_sanitized_transformation(
        domain=domain,
        exact_rows=rows,
        sanitized_rows=sanitized_rows,
        trace_export=trace_export,
    )

    run_id = report.get("run_id")
    if (
        envelope.get("version") != 2
        or envelope.get("run_id") != run_id
        or planner.get("run_id") != run_id
        or plan.get("run_id") != run_id
        or envelope.get("application_source") != report.get("application_source")
    ):
        raise ValueError(f"{domain} run identity or source manifest binding failed")

    bound_files = envelope.get("bound_files") or {}
    expected_bound = {
        "harness_report": report_path,
        "planner_contract": planner_path,
        "compiled_plan": plan_path,
    }
    for key, path in expected_bound.items():
        if (bound_files.get(key) or {}).get("sha256") != sha256_file(path):
            raise ValueError(f"{domain} run envelope does not bind {key}")
    trace_binding = envelope.get("trace") or {}
    if (
        trace_binding.get("sha256") != sha256_file(trace_path)
        or trace_binding.get("head") != exact_verification.get("head")
        or trace_binding.get("rows") != len(rows)
        or trace_binding.get("fully_sealed") is not True
    ):
        raise ValueError(f"{domain} run envelope does not bind the exact trace")

    model_events = envelope.get("model_events") or {}
    event_bindings = {
        "request_hashes": "model_request",
        "response_hashes": "model_response",
        "tool_call_hashes": "agent_tool_call",
    }
    for key, event in event_bindings.items():
        if model_events.get(key) != _event_hashes(rows, event):
            raise ValueError(f"{domain} model event binding failed: {event}")
    if envelope.get("run_completed_hashes") != _event_hashes(rows, "run_completed"):
        raise ValueError(f"{domain} completion event binding failed")
    completions = [
        row for row in rows if row.get("event") == "run_completed"
    ]
    if (
        len(completions) != 1
        or canonical_json((completions[0].get("payload") or {}).get("report"))
        != canonical_json(report)
    ):
        raise ValueError(f"{domain} completed report is not exact")

    evaluations = envelope.get("evaluations") or []
    expected_evaluations = EXPECTED_EVALUATIONS[domain]
    evaluation_by_label = {
        str(evaluation.get("run_label") or ""): evaluation
        for evaluation in evaluations
        if isinstance(evaluation, dict)
    }
    if (
        len(evaluation_by_label) != len(evaluations)
        or set(evaluation_by_label) != set(expected_evaluations)
    ):
        raise ValueError(f"{domain} public evaluation set is incomplete or duplicated")
    completed = [
        row for row in rows if row.get("event") == "public_evaluation_completed"
    ]
    completed_by_label = {
        str((row.get("payload") or {}).get("run_label") or ""): row
        for row in completed
    }
    if (
        len(completed_by_label) != len(completed)
        or set(completed_by_label) != set(expected_evaluations)
    ):
        raise ValueError(f"{domain} trace evaluation set is incomplete or duplicated")

    feedback_by_label: dict[str, dict[str, Any]] = {}
    for evaluation in evaluations:
        feedback_path = domain_root / Path(
            str(evaluation.get("feedback_path") or "")
        ).name
        playwright_path = domain_root / Path(
            str(evaluation.get("playwright_path") or "")
        ).name
        if (
            not feedback_path.is_file()
            or not playwright_path.is_file()
            or evaluation.get("feedback_sha256") != sha256_file(feedback_path)
            or evaluation.get("playwright_sha256") != sha256_file(playwright_path)
        ):
            raise ValueError(
                f"{domain} exported public evaluation is missing or changed"
            )
        feedback = read_json_object(feedback_path)
        label = str(evaluation.get("run_label") or "")
        if (
            feedback.get("run_label") != label
            or feedback.get("fixture_profile") != expected_evaluations[label]
            or feedback.get("playwright_report_sha256")
            != sha256_file(playwright_path)
            or feedback.get("application_source_sha256")
            != (envelope.get("application_source") or {}).get("sha256")
        ):
            raise ValueError(f"{domain} public evaluation cross-binding failed")
        event = completed_by_label[label].get("payload") or {}
        if (
            event.get("evidence_sha256") != sha256_file(feedback_path)
            or event.get("playwright_report_sha256")
            != sha256_file(playwright_path)
            or event.get("application_source_sha256")
            != feedback.get("application_source_sha256")
            or event.get("test_bundle_sha256")
            != feedback.get("test_bundle_sha256")
            or canonical_json(event.get("playwright_report_contract"))
            != canonical_json(feedback.get("playwright_report_contract"))
            or canonical_json(event.get("playwright_runtime"))
            != canonical_json(feedback.get("playwright_runtime"))
            or event.get("fixture_contract_sha256")
            != feedback.get("fixture_contract_sha256")
        ):
            raise ValueError(f"{domain} public evaluation trace binding failed")
        feedback_by_label[label] = feedback

    capsule = (envelope.get("derived_artifacts") or {}).get(
        "capability_capsule"
    ) or {}
    capsule_path = domain_root / "capability-capsule.json"
    if not capsule_path.is_file() or capsule.get("sha256") != sha256_file(
        capsule_path
    ):
        raise ValueError(f"{domain} capability capsule binding failed")
    capsule_payload = verify_capability_capsule(capsule_path)
    capsule_evidence = {
        str(item.get("run_label") or ""): item
        for item in capsule_payload.get("evidence") or []
        if isinstance(item, dict)
    }
    if (
        capsule_payload.get("domain") != domain
        or capsule_payload.get("source_run_id") != run_id
        or capsule_payload.get("source_revision")
        != (report.get("source_identity") or {}).get("revision")
        or capsule_payload.get("requirement_sha256")
        != report.get("requirement_sha256")
        or canonical_json(capsule_payload.get("application_source"))
        != canonical_json(envelope.get("application_source"))
        or canonical_json(capsule_payload.get("capability_shape"))
        != canonical_json(capability_shape(report.get("capability_coverage") or {}))
        or set(capsule_evidence) != set(expected_evaluations)
    ):
        raise ValueError(f"{domain} capability capsule semantics are not source-bound")
    for label, evidence in capsule_evidence.items():
        evaluation = evaluation_by_label[label]
        feedback = feedback_by_label[label]
        if (
            evidence.get("fixture_profile") != expected_evaluations[label]
            or evidence.get("feedback_sha256")
            != evaluation.get("feedback_sha256")
            or evidence.get("playwright_report_sha256")
            != evaluation.get("playwright_sha256")
            or evidence.get("test_bundle_sha256")
            != feedback.get("test_bundle_sha256")
        ):
            raise ValueError(f"{domain} capability capsule evidence is not exact")
    return {
        "run_id": run_id,
        "trace_rows": len(rows),
        "trace_head": exact_verification.get("head"),
        "application_source_sha256": (envelope.get("application_source") or {}).get(
            "sha256"
        ),
        "public_evaluations": len(envelope.get("evaluations") or []),
        "model_requests": len(_event_hashes(rows, "model_request")),
    }


def _qualification_inputs(
    qualification: dict[str, Any],
) -> tuple[tuple[str, ...] | None, str | None, str | None, float, float]:
    if (
        qualification.get("version") != 2
        or qualification.get("gate") != "factory26-public-qualification-v2"
    ):
        raise ValueError("qualification report has an unsupported gate")
    model_policy = qualification.get("model_policy")
    thresholds = qualification.get("thresholds")
    if not isinstance(model_policy, dict) or not isinstance(thresholds, dict):
        raise ValueError("qualification policy or thresholds are missing")
    allowed_value = model_policy.get("allowed_models")
    if allowed_value is None:
        allowed_models = None
    elif (
        isinstance(allowed_value, list)
        and allowed_value
        and all(isinstance(item, str) and item.strip() for item in allowed_value)
    ):
        allowed_models = tuple(allowed_value)
    else:
        raise ValueError("qualification model allowlist is malformed")
    host = model_policy.get("required_gateway_host")
    provenance = model_policy.get("required_gateway_provenance")
    if host is not None and (not isinstance(host, str) or not host.strip()):
        raise ValueError("qualification gateway host pin is malformed")
    if provenance is not None and (
        not isinstance(provenance, str) or not provenance.strip()
    ):
        raise ValueError("qualification provenance pin is malformed")
    try:
        github_max = float(thresholds["github_max_seconds"])
        sheet_max = float(thresholds["sheet_max_seconds"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("qualification duration thresholds are malformed") from exc
    if not all(
        math.isfinite(value) and value > 0 for value in (github_max, sheet_max)
    ):
        raise ValueError("qualification duration thresholds must be positive")
    return allowed_models, host, provenance, github_max, sheet_max


def _require_recomputed_checks(
    *, label: str, recorded: dict[str, Any], recomputed: dict[str, Any]
) -> None:
    if recomputed.get("passed") is not True:
        failed = [
            item.get("name")
            for item in recomputed.get("checks") or []
            if isinstance(item, dict) and item.get("passed") is not True
        ]
        raise ValueError(f"independent qualification failed for {label}: {failed}")
    recorded_by_name = {
        str(item.get("name") or ""): item
        for item in recorded.get("checks") or []
        if isinstance(item, dict)
    }
    for check in recomputed.get("checks") or []:
        name = str(check.get("name") or "")
        recorded_check = recorded_by_name.get(name) or {}
        if (
            recorded_check.get("passed") is not True
            or canonical_json(recorded_check.get("expected"))
            != canonical_json(check.get("expected"))
        ):
            raise ValueError(f"qualification check was not reproducible: {label}/{name}")


def _recompute_qualification(root: Path, qualification: dict[str, Any]) -> None:
    (
        allowed_models,
        expected_gateway_host,
        expected_gateway_provenance,
        github_max,
        sheet_max,
    ) = _qualification_inputs(qualification)
    recorded = qualification.get("evidence") or {}
    reports = {
        "github": read_json_object(root / "github" / "harness-report.json"),
        "sheet": read_json_object(root / "sheet" / "harness-report.json"),
    }
    for domain, expected_requirements, expected_evaluations in (
        ("github", 47, 2),
        ("sheet", 24, 1),
    ):
        report = reports[domain]
        gateway = report.get("model_gateway") or {}
        model = str(gateway.get("model") or "")
        if allowed_models and model not in allowed_models:
            raise ValueError(f"{domain} model is outside the recorded allowlist")
        recomputed = evaluate_generation(
            root / domain / "harness-report.json",
            expected_requirements=expected_requirements,
            expected_requirement_sha256=PUBLIC_REQUIREMENT_SHA256[domain],
            trace_path=root / domain / "production-trace.jsonl",
            expected_public_evaluations=expected_evaluations,
            expected_domain=domain,
            allowed_models=allowed_models,
            expected_gateway_host=expected_gateway_host,
            expected_gateway_provenance=expected_gateway_provenance,
            require_clean_source=True,
            require_bound_artifacts=False,
        )
        _require_recomputed_checks(
            label=f"{domain}_generation",
            recorded=recorded[f"{domain}_generation"],
            recomputed=recomputed,
        )

    evaluation_inputs = (
        ("github_baseline", "github", "github", "baseline", 101, github_max),
        (
            "github_adversarial",
            "github",
            "github.adversarial",
            "adversarial",
            101,
            github_max,
        ),
        ("sheet_baseline", "sheet", "sheet", "baseline", 102, sheet_max),
    )
    for label, domain, run_label, profile, tests, maximum in evaluation_inputs:
        report = reports[domain]
        recomputed = evaluate_run(
            root / domain / f"{run_label}.feedback.json",
            expected_tests=tests,
            expected_profile=profile,
            max_duration_seconds=maximum,
            expected_source_run_id=str(report.get("run_id") or ""),
            expected_application_source_sha256=(
                report.get("application_source") or {}
            ).get("sha256"),
            expected_test_bundle_sha256=PUBLIC_TEST_BUNDLE_SHA256[domain],
            expected_requirement_sha256=PUBLIC_REQUIREMENT_SHA256[domain],
            expected_task_id=domain,
            require_bound_evidence=True,
        )
        _require_recomputed_checks(
            label=label,
            recorded=recorded[label],
            recomputed=recomputed,
        )


def verify_evidence_bundle(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    manifest_path = root / "manifest.json"
    manifest = read_json_object(manifest_path)
    if manifest.get("version") != 2:
        raise ValueError("unsupported evidence manifest version")
    files = manifest.get("files") or []
    if not isinstance(files, list) or not files:
        raise ValueError("evidence manifest has no files")
    seen: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("evidence manifest contains an invalid file row")
        relative = str(item.get("path") or "")
        if relative in seen:
            raise ValueError(f"duplicate evidence manifest path: {relative}")
        seen.add(relative)
        path = _safe_bundle_path(root, relative)
        if item.get("sha256") != sha256_file(path) or item.get("bytes") != path.stat().st_size:
            raise ValueError(f"evidence file hash or size mismatch: {relative}")
    if seen != EXPECTED_MANIFEST_FILES:
        raise ValueError("evidence manifest file set is incomplete or unexpected")
    observed_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != manifest_path
    }
    if observed_files != EXPECTED_MANIFEST_FILES:
        raise ValueError("evidence directory contains unlisted or missing files")

    qualification_path = root / "qualification.json"
    qualification = read_json_object(qualification_path)
    evidence = qualification.get("evidence") or {}
    if qualification.get("passed") is not True or set(evidence) != set(
        EXPECTED_QUALIFICATION_FILES
    ):
        raise ValueError("qualification report is not complete and green")
    for label, relative in EXPECTED_QUALIFICATION_FILES.items():
        item = evidence.get(label) or {}
        checks = item.get("checks") or []
        target = _safe_bundle_path(root, relative)
        if (
            item.get("passed") is not True
            or not checks
            or not all(
                isinstance(check, dict) and check.get("passed") is True
                for check in checks
            )
            or item.get("sha256") != sha256_file(target)
        ):
            raise ValueError(f"qualification evidence failed binding: {label}")
    _recompute_qualification(root, qualification)

    trace_exports = manifest.get("trace_exports") or {}
    if set(trace_exports) != {"github", "sheet"}:
        raise ValueError("trace export metadata must cover both domains")
    domains = {
        domain: _verify_domain(root, domain, trace_exports[domain])
        for domain in ("github", "sheet")
    }
    return {
        "version": 1,
        "kind": "langqi-public-evidence-verification",
        "passed": True,
        "manifest_sha256": sha256_file(manifest_path),
        "file_count": len(files),
        "qualification_gate": qualification.get("gate"),
        "domains": domains,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Independently verify an exported Langqi evidence bundle"
    )
    parser.add_argument("evidence_dir", type=Path)
    args = parser.parse_args()
    try:
        result = verify_evidence_bundle(args.evidence_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "version": 1,
            "kind": "langqi-public-evidence-verification",
            "passed": False,
            "error": str(exc),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
