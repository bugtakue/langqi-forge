from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .trace import ProductionTrace

PUBLIC_REQUIREMENT_SHA256 = {
    "github": "a4ba2c2e1bd62091a46384e89a823819a485ab609780ce00ead1490edd881959",
    "sheet": "9f2bfd7a9242474ac8e5b3ab9bc0e77e7b659b0ac72b5110bddf53a313c2b494",
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check(name: str, passed: bool, actual: Any, expected: Any) -> dict[str, Any]:
    return {"name": name, "passed": passed, "actual": actual, "expected": expected}


def evaluate_run(
    path: Path,
    *,
    expected_tests: int,
    expected_profile: str,
    max_duration_seconds: float,
    expected_source_run_id: str | None = None,
) -> dict[str, Any]:
    payload = _load(path)
    stats = payload.get("stats") or {}
    checks = [
        _check(
            "source_run_id",
            expected_source_run_id is None
            or payload.get("source_run_id") == expected_source_run_id,
            payload.get("source_run_id"),
            expected_source_run_id,
        ),
        _check("exit_code", payload.get("exit_code") == 0, payload.get("exit_code"), 0),
        _check(
            "fixture_profile",
            payload.get("fixture_profile") == expected_profile,
            payload.get("fixture_profile"),
            expected_profile,
        ),
        _check(
            "fully_parallel",
            payload.get("fully_parallel") is True,
            payload.get("fully_parallel"),
            True,
        ),
        _check(
            "expected_tests",
            stats.get("expected") == expected_tests,
            stats.get("expected"),
            expected_tests,
        ),
        _check(
            "unexpected", stats.get("unexpected", 0) == 0, stats.get("unexpected", 0), 0
        ),
        _check("skipped", stats.get("skipped", 0) == 0, stats.get("skipped", 0), 0),
        _check("flaky", stats.get("flaky", 0) == 0, stats.get("flaky", 0), 0),
        _check(
            "duration_seconds",
            float(payload.get("duration_seconds", float("inf")))
            <= max_duration_seconds,
            payload.get("duration_seconds"),
            {"maximum": max_duration_seconds},
        ),
    ]
    return {
        "path": str(path),
        "sha256": _digest(path),
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
    }


def evaluate_generation(
    path: Path,
    *,
    expected_requirements: int,
    expected_requirement_sha256: str | None = None,
    max_prompt_tokens: int = 6_000,
    max_completion_tokens: int = 1_000,
) -> dict[str, Any]:
    payload = _load(path)
    usage = payload.get("model_usage") or {}
    contract = payload.get("planner_contract") or {}
    source_identity = payload.get("source_identity") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    checks = [
        _check(
            "run_id",
            _valid_run_id(payload.get("run_id")),
            payload.get("run_id"),
            "UUID",
        ),
        _check(
            "source_worktree_not_dirty",
            source_identity.get("worktree_clean") is not False,
            source_identity.get("worktree_clean"),
            "true or unavailable for an unpacked bundle",
        ),
        _check(
            "all_local_checks_passed",
            payload.get("all_local_checks_passed") is True,
            payload.get("all_local_checks_passed"),
            True,
        ),
        _check(
            "run_completed_successfully",
            payload.get("run_completed_successfully") is True,
            payload.get("run_completed_successfully"),
            True,
        ),
        _check(
            "requirement_count",
            payload.get("requirement_count") == expected_requirements,
            payload.get("requirement_count"),
            expected_requirements,
        ),
        _check(
            "requirement_sha256",
            expected_requirement_sha256 is None
            or payload.get("requirement_sha256") == expected_requirement_sha256,
            payload.get("requirement_sha256"),
            expected_requirement_sha256,
        ),
        _check(
            "planner_status",
            payload.get("planner_status") == "completed",
            payload.get("planner_status"),
            "completed",
        ),
        _check(
            "execution_route",
            payload.get("execution_route") == "planner-approved-deterministic-kernel",
            payload.get("execution_route"),
            "planner-approved-deterministic-kernel",
        ),
        _check(
            "planner_decision_mode",
            contract.get("decision_mode") == "tool_call",
            contract.get("decision_mode"),
            "tool_call",
        ),
        _check(
            "model_request_count",
            usage.get("request_count") == 1,
            usage.get("request_count"),
            1,
        ),
        _check(
            "model_http_attempt_count",
            usage.get("http_attempt_count") == 1,
            usage.get("http_attempt_count"),
            1,
        ),
        _check(
            "prompt_tokens",
            0 < prompt_tokens <= max_prompt_tokens,
            prompt_tokens,
            {"minimum": 1, "maximum": max_prompt_tokens},
        ),
        _check(
            "completion_tokens",
            0 < completion_tokens <= max_completion_tokens,
            completion_tokens,
            {"minimum": 1, "maximum": max_completion_tokens},
        ),
        _check(
            "planner_iterations",
            payload.get("planner_iterations") == 1,
            payload.get("planner_iterations"),
            1,
        ),
        _check(
            "coding_agent_iterations",
            payload.get("coding_agent_iterations") == 0,
            payload.get("coding_agent_iterations"),
            0,
        ),
        _check(
            "manual_interventions",
            payload.get("manual_interventions") == 0,
            payload.get("manual_interventions"),
            0,
        ),
    ]
    return {
        "path": str(path),
        "sha256": _digest(path),
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
    }


def _valid_run_id(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def qualify(
    github_project: Path,
    sheet_project: Path,
    *,
    github_max_seconds: float = 20.0,
    sheet_max_seconds: float = 30.0,
) -> dict[str, Any]:
    github_root = github_project.resolve()
    sheet_root = sheet_project.resolve()
    github_report = _load(github_root / ".arc" / "harness-report.json")
    sheet_report = _load(sheet_root / ".arc" / "harness-report.json")
    github_run_id = str(github_report.get("run_id") or "")
    sheet_run_id = str(sheet_report.get("run_id") or "")
    evidence = {
        "github_generation": evaluate_generation(
            github_root / ".arc" / "harness-report.json",
            expected_requirements=47,
            expected_requirement_sha256=PUBLIC_REQUIREMENT_SHA256["github"],
        ),
        "sheet_generation": evaluate_generation(
            sheet_root / ".arc" / "harness-report.json",
            expected_requirements=24,
            expected_requirement_sha256=PUBLIC_REQUIREMENT_SHA256["sheet"],
        ),
        "github_baseline": evaluate_run(
            github_root / ".arc" / "public-eval" / "github.feedback.json",
            expected_tests=101,
            expected_profile="baseline",
            max_duration_seconds=github_max_seconds,
            expected_source_run_id=github_run_id,
        ),
        "github_adversarial": evaluate_run(
            github_root / ".arc" / "public-eval" / "github.adversarial.feedback.json",
            expected_tests=101,
            expected_profile="adversarial",
            max_duration_seconds=github_max_seconds,
            expected_source_run_id=github_run_id,
        ),
        "sheet_baseline": evaluate_run(
            sheet_root / ".arc" / "public-eval" / "sheet.feedback.json",
            expected_tests=102,
            expected_profile="baseline",
            max_duration_seconds=sheet_max_seconds,
            expected_source_run_id=sheet_run_id,
        ),
    }
    display_paths = {
        "github_generation": ".arc/harness-report.json",
        "sheet_generation": ".arc/harness-report.json",
        "github_baseline": ".arc/public-eval/github.feedback.json",
        "github_adversarial": ".arc/public-eval/github.adversarial.feedback.json",
        "sheet_baseline": ".arc/public-eval/sheet.feedback.json",
    }
    for name, display_path in display_paths.items():
        evidence[name]["path"] = display_path
    return {
        "version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "gate": "factory26-public-qualification-v1",
        "passed": all(item["passed"] for item in evidence.values()),
        "evidence": evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed Factory26 public qualification gate"
    )
    parser.add_argument("--github-project", type=Path, required=True)
    parser.add_argument("--sheet-project", type=Path, required=True)
    parser.add_argument("--github-max-seconds", type=float, default=20.0)
    parser.add_argument("--sheet-max-seconds", type=float, default=30.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    trace_paths = (
        args.github_project.resolve() / ".arc" / "production-trace.jsonl",
        args.sheet_project.resolve() / ".arc" / "production-trace.jsonl",
    )
    for trace_path in trace_paths:
        ProductionTrace(trace_path).record(
            "qualification_gate_started",
            gate="factory26-public-qualification-v1",
            prompt_invocations=0,
            agent_iterations=0,
            manual_interventions=0,
        )
    report = qualify(
        args.github_project,
        args.sheet_project,
        github_max_seconds=args.github_max_seconds,
        sheet_max_seconds=args.sheet_max_seconds,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(rendered, encoding="utf-8")
        temporary.replace(args.output)
    failed_checks = {
        name: [check["name"] for check in item["checks"] if not check["passed"]]
        for name, item in report["evidence"].items()
        if not item["passed"]
    }
    for trace_path in trace_paths:
        ProductionTrace(trace_path).record(
            "qualification_gate_completed",
            gate=report["gate"],
            passed=report["passed"],
            evidence_sha256={
                name: item["sha256"] for name, item in report["evidence"].items()
            },
            failed_checks=failed_checks,
        )
    print(rendered, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
