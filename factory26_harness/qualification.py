from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


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
) -> dict[str, Any]:
    payload = _load(path)
    stats = payload.get("stats") or {}
    checks = [
        _check("exit_code", payload.get("exit_code") == 0, payload.get("exit_code"), 0),
        _check("fixture_profile", payload.get("fixture_profile") == expected_profile, payload.get("fixture_profile"), expected_profile),
        _check("fully_parallel", payload.get("fully_parallel") is True, payload.get("fully_parallel"), True),
        _check("expected_tests", stats.get("expected") == expected_tests, stats.get("expected"), expected_tests),
        _check("unexpected", stats.get("unexpected", 0) == 0, stats.get("unexpected", 0), 0),
        _check("skipped", stats.get("skipped", 0) == 0, stats.get("skipped", 0), 0),
        _check("flaky", stats.get("flaky", 0) == 0, stats.get("flaky", 0), 0),
        _check(
            "duration_seconds",
            float(payload.get("duration_seconds", float("inf"))) <= max_duration_seconds,
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


def evaluate_generation(path: Path, *, expected_requirements: int) -> dict[str, Any]:
    payload = _load(path)
    usage = payload.get("model_usage") or {}
    checks = [
        _check("all_local_checks_passed", payload.get("all_local_checks_passed") is True, payload.get("all_local_checks_passed"), True),
        _check("requirement_count", payload.get("requirement_count") == expected_requirements, payload.get("requirement_count"), expected_requirements),
        _check("prompt_tokens", usage.get("prompt_tokens") == 0, usage.get("prompt_tokens"), 0),
        _check("completion_tokens", usage.get("completion_tokens") == 0, usage.get("completion_tokens"), 0),
    ]
    return {
        "path": str(path),
        "sha256": _digest(path),
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
    }


def qualify(
    github_project: Path,
    sheet_project: Path,
    *,
    github_max_seconds: float = 20.0,
    sheet_max_seconds: float = 30.0,
) -> dict[str, Any]:
    github_root = github_project.resolve()
    sheet_root = sheet_project.resolve()
    evidence = {
        "github_generation": evaluate_generation(
            github_root / ".arc" / "harness-report.json", expected_requirements=47
        ),
        "sheet_generation": evaluate_generation(
            sheet_root / ".arc" / "harness-report.json", expected_requirements=24
        ),
        "github_baseline": evaluate_run(
            github_root / ".arc" / "public-eval" / "github.feedback.json",
            expected_tests=101,
            expected_profile="baseline",
            max_duration_seconds=github_max_seconds,
        ),
        "github_adversarial": evaluate_run(
            github_root / ".arc" / "public-eval" / "github.adversarial.feedback.json",
            expected_tests=101,
            expected_profile="adversarial",
            max_duration_seconds=github_max_seconds,
        ),
        "sheet_baseline": evaluate_run(
            sheet_root / ".arc" / "public-eval" / "sheet.feedback.json",
            expected_tests=102,
            expected_profile="baseline",
            max_duration_seconds=sheet_max_seconds,
        ),
    }
    return {
        "version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "gate": "factory26-public-qualification-v1",
        "passed": all(item["passed"] for item in evidence.values()),
        "evidence": evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed Factory26 public qualification gate")
    parser.add_argument("--github-project", type=Path, required=True)
    parser.add_argument("--sheet-project", type=Path, required=True)
    parser.add_argument("--github-max-seconds", type=float, default=20.0)
    parser.add_argument("--sheet-max-seconds", type=float, default=30.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
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
    print(rendered, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
