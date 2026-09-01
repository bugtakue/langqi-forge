#!/usr/bin/env python3
"""Run one model-backed, hidden-test generalization challenge."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from factory26_harness.artifacts import (
    application_source_manifest,
    sha256_file,
    verify_run_envelope,
    write_run_envelope,
)
from factory26_harness.feedback import (
    parse_playwright_json,
    validate_playwright_report,
)
from factory26_harness.public_eval import (
    _backend_environment,
    _evaluation_environment,
    _playwright_runtime_contract,
    _wait_ready,
    _write,
    ensure_playwright,
)
from factory26_harness.trace import ProductionTrace


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CHALLENGE_ROOT = REPOSITORY_ROOT / "benchmarks" / "generalization" / "change-control"
REQUIREMENTS_PATH = CHALLENGE_ROOT / "requirements.yaml"
TEST_SOURCE = CHALLENGE_ROOT / "tests" / "change-control.spec.ts"
REQUIREMENTS_SHA256 = "24bb00980efa8b0ad98088d91cebce74bf5d851f90f4d7025fbee2cef0b7597c"
TEST_SOURCE_SHA256 = "eef8ca61fd25092b6e084c6189586577eb0d7910deaba8b67ccad27f34887ba0"
TEST_INVENTORY_SHA256 = (
    "e4e415ab4c80d4db880a94de91304ddb1323974c23944a5c971e1943f88df1f8"
)
EXPECTED_TEST_COUNT = 5
EXPECTED_ROUTE = "planner-routed-bounded-code-agent"


def _locked_file(path: Path, expected_sha256: str) -> None:
    if not path.is_file() or sha256_file(path) != expected_sha256:
        raise ValueError(f"generalization input differs from its locked hash: {path}")


def _stop(process: subprocess.Popen[Any]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


def _resolve_agent_root(agent_root: Path) -> Path:
    resolved = agent_root.expanduser().resolve()
    if not (resolved / "main.py").is_file():
        raise ValueError("generalization agent root must contain main.py")
    return resolved


def _generate(
    output_dir: Path,
    web_port: int,
    smoke_port: int,
    *,
    agent_root: Path,
) -> None:
    if output_dir.exists():
        raise ValueError("generalization output directory must not already exist")
    completed = subprocess.run(
        [
            sys.executable,
            str(agent_root / "main.py"),
            str(REQUIREMENTS_PATH),
            "--output-dir",
            str(output_dir),
            "--web-port",
            str(web_port),
            "--smoke-port",
            str(smoke_port),
            "--batch-size",
            "2",
            "--max-agent-turns",
            "18",
            "--strict-exit",
        ],
        cwd=agent_root,
        env=dict(os.environ),
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "model-backed generalization generation failed:\n"
            + ((completed.stdout or "") + "\n" + (completed.stderr or ""))[-6000:]
        )


def run_challenge(
    output_dir: Path,
    cache_root: Path,
    *,
    web_port: int,
    smoke_port: int,
    agent_root: Path = REPOSITORY_ROOT,
) -> dict[str, Any]:
    output_dir = output_dir.expanduser().resolve()
    cache_root = cache_root.expanduser().resolve()
    agent_root = _resolve_agent_root(agent_root)
    _locked_file(REQUIREMENTS_PATH, REQUIREMENTS_SHA256)
    _locked_file(TEST_SOURCE, TEST_SOURCE_SHA256)
    _generate(
        output_dir,
        web_port,
        smoke_port,
        agent_root=agent_root,
    )

    report_path = output_dir / ".arc" / "harness-report.json"
    harness_report = json.loads(report_path.read_text(encoding="utf-8"))
    model_usage = harness_report.get("model_usage") or {}
    source_identity = harness_report.get("source_identity") or {}
    if (
        harness_report.get("dry_run") is not False
        or harness_report.get("detected_domain") != "generic"
        or harness_report.get("planner_status") != "completed"
        or harness_report.get("execution_route") != EXPECTED_ROUTE
        or int(harness_report.get("coding_agent_iterations") or 0) < 1
        or int(harness_report.get("manual_interventions") or 0) != 0
        or harness_report.get("all_local_checks_passed") is not True
        or int(model_usage.get("request_count") or 0) < 2
        or int(model_usage.get("http_attempt_count") or 0)
        < int(model_usage.get("request_count") or 0)
        or source_identity.get("worktree_clean") is not True
    ):
        raise RuntimeError(
            "generated run did not exercise the bounded generic agent lane"
        )
    planner_contract = harness_report.get("planner_contract") or {}
    if (
        planner_contract.get("domain") != "generic"
        or planner_contract.get("kernel_eligible") is not False
        or set(planner_contract.get("uncovered_requirement_ids") or [])
        != {"REQ-GEN-1", "REQ-GEN-2"}
    ):
        raise RuntimeError(
            "planner did not explicitly identify the unseen requirements"
        )

    verify_run_envelope(output_dir)
    source_before = application_source_manifest(output_dir)
    runtime_cli = ensure_playwright(cache_root)
    runtime_before = _playwright_runtime_contract(cache_root)
    synced_test_dir = cache_root / "generalization-change-control" / "tests"
    synced_test = synced_test_dir / TEST_SOURCE.name
    _write(synced_test, TEST_SOURCE.read_text(encoding="utf-8"))
    _locked_file(synced_test, TEST_SOURCE_SHA256)

    environment = _evaluation_environment(
        E2E_BASE_URL=f"http://127.0.0.1:{web_port}",
        FACTORY26_PUBLIC_TEST_DIR=str(synced_test_dir),
        FACTORY26_PUBLIC_TEST_TIMEOUT="10000",
        FACTORY26_PUBLIC_EXPECT_TIMEOUT="5000",
        FACTORY26_PUBLIC_WORKERS="1",
        FACTORY26_PUBLIC_FULLY_PARALLEL="0",
    )
    backend_log_path = output_dir / ".arc" / "generalization-eval" / "backend.log"
    backend_log_path.parent.mkdir(parents=True, exist_ok=True)
    with backend_log_path.open("w", encoding="utf-8") as backend_log:
        process = subprocess.Popen(
            ["npm", "start"],
            cwd=output_dir / "backend",
            env=_backend_environment(web_port, {}),
            stdout=backend_log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            _wait_ready(web_port, process)
            started = time.monotonic()
            completed = subprocess.run(
                [
                    "node",
                    str(runtime_cli),
                    "test",
                    "--config",
                    str(cache_root / "playwright.config.mjs"),
                ],
                cwd=cache_root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            duration_seconds = time.monotonic() - started
        finally:
            _stop(process)

    if _playwright_runtime_contract(cache_root) != runtime_before:
        raise RuntimeError(
            "Playwright runtime changed during generalization evaluation"
        )
    _locked_file(synced_test, TEST_SOURCE_SHA256)
    if application_source_manifest(output_dir) != source_before:
        raise RuntimeError("generalization evaluation mutated generated source")

    raw_path = output_dir / ".arc" / "generalization-eval" / "playwright.json"
    stderr_path = output_dir / ".arc" / "generalization-eval" / "playwright.stderr.log"
    _write(raw_path, completed.stdout)
    _write(stderr_path, completed.stderr)
    try:
        raw = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("generalization evaluator did not emit JSON") from exc
    raw_contract = validate_playwright_report(
        raw,
        expected_test_files={TEST_SOURCE.name},
        expected_test_count=EXPECTED_TEST_COUNT,
        expected_inventory_sha256=TEST_INVENTORY_SHA256,
        expected_workers=1,
        expected_fully_parallel=False,
    )
    failures = parse_playwright_json(raw)
    stats = raw.get("stats") or {}
    passed = (
        completed.returncode == 0
        and stats.get("expected") == EXPECTED_TEST_COUNT
        and stats.get("unexpected") == 0
        and stats.get("skipped") == 0
        and stats.get("flaky") == 0
        and not failures
    )
    proof = {
        "version": 1,
        "claim": "independent unseen-domain generalization proof; not an official score",
        "passed": passed,
        "run_id": harness_report.get("run_id"),
        "source_revision": source_identity.get("revision"),
        "requirements_sha256": REQUIREMENTS_SHA256,
        "test_source_sha256": TEST_SOURCE_SHA256,
        "playwright_report_sha256": sha256_file(raw_path),
        "playwright_report_contract": raw_contract,
        "playwright_runtime": runtime_before,
        "application_source": source_before,
        "model_gateway": harness_report.get("model_gateway"),
        "model_usage": model_usage,
        "planner_iterations": harness_report.get("planner_iterations"),
        "coding_agent_iterations": harness_report.get("coding_agent_iterations"),
        "manual_interventions": harness_report.get("manual_interventions"),
        "execution_route": harness_report.get("execution_route"),
        "duration_seconds": round(duration_seconds, 3),
        "exit_code": completed.returncode,
        "stats": stats,
        "failure_count": len(failures),
    }
    proof_path = output_dir / ".arc" / "generalization-eval" / "proof.json"
    _write(proof_path, json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
    trace = ProductionTrace(output_dir / ".arc" / "production-trace.jsonl")
    trace.record(
        "generalization_evaluation_completed",
        passed=passed,
        challenge="change-control-v1",
        evidence_file=".arc/generalization-eval/proof.json",
        evidence_sha256=sha256_file(proof_path),
        playwright_report_sha256=proof["playwright_report_sha256"],
        application_source_sha256=source_before["sha256"],
        model_requests=model_usage.get("request_count"),
        coding_agent_iterations=harness_report.get("coding_agent_iterations"),
        manual_interventions=harness_report.get("manual_interventions"),
    )
    write_run_envelope(output_dir)
    if not passed:
        raise RuntimeError(f"unseen-domain GUI failed with {len(failures)} failure(s)")
    return proof


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the model-backed Langqi Forge unseen-domain proof"
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--cache", type=Path, default=REPOSITORY_ROOT / ".cache" / "public-tasks"
    )
    parser.add_argument("--web-port", type=int, default=3601)
    parser.add_argument("--smoke-port", type=int, default=3602)
    parser.add_argument(
        "--agent-root",
        type=Path,
        default=REPOSITORY_ROOT,
        help="Agent source or exact unpacked submission bundle containing main.py",
    )
    args = parser.parse_args()
    proof = run_challenge(
        args.output_dir,
        args.cache,
        web_port=args.web_port,
        smoke_port=args.smoke_port,
        agent_root=args.agent_root,
    )
    print(json.dumps(proof, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
