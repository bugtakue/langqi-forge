from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .artifacts import (
    atomic_write_json,
    canonical_json,
    sha256_bytes,
    sha256_file,
    verify_run_envelope,
    write_run_envelope,
)
from .capabilities import CAPABILITY_CATALOG, CoverageAnalysis
from .trace import ProductionTrace


CAPSULE_VERSION = 1
REQUIRED_PROFILES = {
    "github": frozenset({"baseline", "adversarial"}),
    "sheet": frozenset({"baseline"}),
}


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _capsule_id(payload: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "capsule_id"}
    return sha256_bytes(canonical_json(unsigned))


def capability_shape(coverage: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for requirement in coverage.get("requirements") or []:
        if not isinstance(requirement, dict):
            continue
        rows.append(sorted(str(item) for item in requirement.get("capabilities") or []))
    rows.sort()
    return {
        "algorithm": "sorted-capability-multiset-v1",
        "sha256": sha256_bytes(canonical_json(rows)),
        "atomic_shapes": rows,
    }


def _green_feedback(path: Path, source_sha256: str) -> dict[str, Any]:
    feedback = _load(path)
    label = str(feedback.get("run_label") or "")
    raw_path = path.parent / f"{label}.playwright.json"
    raw = _load(raw_path)
    stats = feedback.get("stats") or {}
    raw_stats = raw.get("stats") or {}
    passed = (
        feedback.get("version") == 2
        and feedback.get("exit_code") == 0
        and feedback.get("failure_count") == 0
        and feedback.get("application_source_sha256") == source_sha256
        and feedback.get("playwright_report_sha256") == sha256_file(raw_path)
        and canonical_json(stats) == canonical_json(raw_stats)
        and stats.get("unexpected", 0) == 0
        and stats.get("skipped", 0) == 0
        and stats.get("flaky", 0) == 0
        and int(stats.get("expected") or 0) > 0
    )
    if not passed:
        raise ValueError(f"evaluation is not green and source-bound: {path}")
    return {
        "run_label": label,
        "fixture_profile": feedback.get("fixture_profile"),
        "expected_tests": stats.get("expected"),
        "test_bundle_sha256": feedback.get("test_bundle_sha256"),
        "playwright_report_sha256": feedback.get("playwright_report_sha256"),
        "feedback_sha256": sha256_file(path),
    }


def forge_capability_capsule(project_dir: Path) -> dict[str, Any] | None:
    project_dir = project_dir.resolve()
    envelope = verify_run_envelope(project_dir)
    report = _load(project_dir / ".arc" / "harness-report.json")
    coverage = report.get("capability_coverage") or {}
    domain = str(coverage.get("domain") or "")
    required_profiles = REQUIRED_PROFILES.get(domain)
    if required_profiles is None:
        return None
    if (
        coverage.get("kernel_eligible") is not True
        or coverage.get("uncovered_requirement_ids") != []
        or coverage.get("missing_capabilities") != []
    ):
        raise ValueError("capability gaps prevent capsule promotion")

    evaluations = []
    public_root = project_dir / ".arc" / "public-eval"
    for feedback_path in sorted(public_root.glob("*.feedback.json")):
        evaluations.append(
            _green_feedback(
                feedback_path,
                str((envelope.get("application_source") or {}).get("sha256") or ""),
            )
        )
    profiles = {str(item.get("fixture_profile") or "") for item in evaluations}
    if not required_profiles.issubset(profiles):
        return None

    by_id = {item.capability_id: item for item in CAPABILITY_CATALOG.get(domain, ())}
    required_capabilities = sorted(
        str(item) for item in coverage.get("required_capabilities") or []
    )
    if not required_capabilities or any(item not in by_id for item in required_capabilities):
        raise ValueError("capsule names an unknown capability")
    capabilities = [
        {
            "id": capability_id,
            "version": by_id[capability_id].version,
            "behavior_clauses": list(by_id[capability_id].behavior_clauses),
            "exclusions": list(by_id[capability_id].exclusions),
        }
        for capability_id in required_capabilities
    ]
    payload: dict[str, Any] = {
        "version": CAPSULE_VERSION,
        "kind": "falsifiable-capability-capsule",
        "domain": domain,
        "source_run_id": report.get("run_id"),
        "source_revision": (report.get("source_identity") or {}).get("revision"),
        "requirement_sha256": report.get("requirement_sha256"),
        "application_source": envelope.get("application_source"),
        "capability_shape": capability_shape(coverage),
        "capabilities": capabilities,
        "evidence": sorted(evaluations, key=lambda item: item["run_label"]),
        "promotion_gate": {
            "required_profiles": sorted(required_profiles),
            "observed_profiles": sorted(profiles),
            "all_observed_evaluations_green": True,
            "source_bound": True,
            "raw_reports_bound": True,
        },
        "reuse_policy": {
            "match": "same domain; current required capabilities are a version-equal subset; zero uncovered requirements",
            "skips_revalidation": False,
            "effect": "adds provisional prior evidence to route selection; no validation is skipped",
        },
        "claim_boundary": (
            "This capsule records falsifiable evidence for one source tree and public test bundles. "
            "Reuse is provisional until the new requirement variant is independently re-evaluated."
        ),
    }
    payload["capsule_id"] = _capsule_id(payload)
    capsule_path = project_dir / ".arc" / "capability-capsule.json"
    if capsule_path.is_file():
        existing = verify_capability_capsule(capsule_path)
        if canonical_json(existing) != canonical_json(payload):
            raise ValueError("an existing capability capsule differs from current evidence")
        return existing
    atomic_write_json(capsule_path, payload)
    capsule_sha256 = sha256_file(capsule_path)
    ProductionTrace(project_dir / ".arc" / "production-trace.jsonl").record(
        "capability_capsule_forged",
        capsule_id=payload["capsule_id"],
        capsule_sha256=capsule_sha256,
        domain=domain,
        required_profiles=sorted(required_profiles),
        prompt_invocations=0,
        agent_iterations=0,
        manual_interventions=0,
    )
    write_run_envelope(project_dir)
    return payload


def verify_capability_capsule(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("capability capsule must be a regular file")
    if path.stat().st_size > 2_000_000:
        raise ValueError("capability capsule exceeds the 2 MB safety limit")
    payload = _load(path)
    if payload.get("version") != CAPSULE_VERSION:
        raise ValueError("unsupported capability capsule version")
    if payload.get("kind") != "falsifiable-capability-capsule":
        raise ValueError("invalid capability capsule kind")
    if payload.get("capsule_id") != _capsule_id(payload):
        raise ValueError("capability capsule id does not match its content")
    domain = str(payload.get("domain") or "")
    catalog = {item.capability_id: item for item in CAPABILITY_CATALOG.get(domain, ())}
    capabilities = payload.get("capabilities") or []
    if not catalog or not isinstance(capabilities, list) or not capabilities:
        raise ValueError("capability capsule is empty")
    for capability in capabilities:
        if not isinstance(capability, dict):
            raise ValueError("capability capsule contains an invalid capability")
        capability_id = str(capability.get("id") or "")
        definition = catalog.get(capability_id)
        if (
            definition is None
            or capability.get("version") != definition.version
            or capability.get("behavior_clauses")
            != list(definition.behavior_clauses)
            or capability.get("exclusions") != list(definition.exclusions)
        ):
            raise ValueError("capability capsule is stale or unknown")
    gate = payload.get("promotion_gate") or {}
    required_profiles = REQUIRED_PROFILES.get(domain)
    gate_required = set(gate.get("required_profiles") or [])
    observed_profiles = set(gate.get("observed_profiles") or [])
    evidence = payload.get("evidence") or []
    evidence_profiles = {
        str(item.get("fixture_profile") or "")
        for item in evidence
        if isinstance(item, dict)
    }
    if (
        required_profiles is None
        or gate_required != set(required_profiles)
        or not isinstance(evidence, list)
        or not evidence
        or evidence_profiles != observed_profiles
        or gate.get("all_observed_evaluations_green") is not True
        or gate.get("source_bound") is not True
        or gate.get("raw_reports_bound") is not True
        or not gate_required.issubset(observed_profiles)
    ):
        raise ValueError("capability capsule promotion gate is incomplete")
    for item in evidence:
        if not isinstance(item, dict) or any(
            not item.get(field)
            for field in (
                "run_label",
                "fixture_profile",
                "test_bundle_sha256",
                "playwright_report_sha256",
                "feedback_sha256",
            )
        ):
            raise ValueError("capability capsule evidence row is incomplete")
    return payload


def match_capability_capsule(
    capsule: dict[str, Any], coverage: CoverageAnalysis
) -> dict[str, Any]:
    reasons = []
    if capsule.get("domain") != coverage.domain:
        reasons.append("domain_mismatch")
    if not coverage.kernel_eligible or coverage.uncovered_requirement_ids:
        reasons.append("uncovered_requirements")
    certified = {
        str(item.get("id") or ""): str(item.get("version") or "")
        for item in capsule.get("capabilities") or []
        if isinstance(item, dict)
    }
    current = {
        item.capability_id: item.version
        for item in CAPABILITY_CATALOG.get(coverage.domain, ())
    }
    for capability_id in coverage.required_capabilities:
        if certified.get(capability_id) != current.get(capability_id):
            reasons.append(f"uncertified_or_stale:{capability_id}")
    return {
        "matched": not reasons,
        "capsule_id": capsule.get("capsule_id"),
        "required_capabilities": list(coverage.required_capabilities),
        "reasons": reasons,
        "revalidation_required": True,
    }


def record_counterexample(
    project_dir: Path,
    *,
    feedback: dict[str, Any],
    repair_packets: list[dict[str, Any]],
) -> tuple[Path, dict[str, Any]]:
    label = str(feedback.get("run_label") or "")
    raw_path = project_dir / ".arc" / "public-eval" / f"{label}.playwright.json"
    representatives = []
    for packet in repair_packets:
        tests = packet.get("tests") or []
        representatives.append(
            {
                "signature": packet.get("signature"),
                "classification": packet.get("classification"),
                "repair_allowed": packet.get("repair_allowed") is True,
                "observed_failure_count": packet.get("failure_count"),
                "representative_test": tests[0] if tests else None,
                "requirement_ids": packet.get("requirement_ids") or [],
                "related_files": packet.get("related_files") or [],
            }
        )
    payload = {
        "version": 1,
        "kind": "minimal-observed-counterexample-set",
        "source_run_id": feedback.get("source_run_id"),
        "run_label": label,
        "fixture_profile": feedback.get("fixture_profile"),
        "application_source_sha256": feedback.get("application_source_sha256"),
        "test_bundle_sha256": feedback.get("test_bundle_sha256"),
        "playwright_report_sha256": sha256_file(raw_path),
        "failure_count": feedback.get("failure_count"),
        "cluster_count": len(representatives),
        "representatives": representatives,
        "claim_boundary": (
            "One observed representative is retained per normalized failure signature; "
            "this is not a proof of globally minimal input."
        ),
    }
    path = project_dir / ".arc" / "counterexamples" / f"{label}.json"
    atomic_write_json(path, payload)
    return path, payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Forge or verify a falsifiable Langqi capability capsule"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    forge = subparsers.add_parser("forge")
    forge.add_argument("--project", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("capsule", type=Path)
    args = parser.parse_args()
    if args.command == "forge":
        result = forge_capability_capsule(args.project)
        if result is None:
            print(json.dumps({"promoted": False, "reason": "required profiles are incomplete"}))
            return 2
    else:
        result = verify_capability_capsule(args.capsule)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
