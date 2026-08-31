from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .artifacts import (
    application_source_manifest,
    public_task_bundle_manifest,
    sha256_file,
    verify_run_envelope,
    write_run_envelope,
)
from .checks import SAFE_ENVIRONMENT_KEYS, failures, run_full_checks
from .capability_memory import forge_capability_capsule, record_counterexample
from .feedback import (
    parse_playwright_json,
    repair_packets,
    validate_playwright_report,
)
from .impact import ChangeImpactGraph
from .public_contract import (
    PLAYWRIGHT_CLI_SHA256,
    PLAYWRIGHT_RUNTIME_FILE_COUNT,
    PLAYWRIGHT_RUNTIME_SHA256,
    PLAYWRIGHT_VERSION,
    PUBLIC_PLAYWRIGHT_INVENTORY_SHA256,
    PUBLIC_TEST_COUNTS,
)
from .public_fixtures import public_fixture_environment
from .trace import ProductionTrace

PLAYWRIGHT_PACKAGE = {
    "name": "factory26-public-eval-cache",
    "private": True,
    "version": "0.0.0",
    "type": "module",
    "devDependencies": {"@playwright/test": PLAYWRIGHT_VERSION},
}

PLAYWRIGHT_RUNTIME_ROOTS = (
    "node_modules/@playwright/test",
    "node_modules/playwright",
    "node_modules/playwright-core",
)
EVALUATION_ENVIRONMENT_KEYS = SAFE_ENVIRONMENT_KEYS | {
    "HOME",
    "USERPROFILE",
    "XDG_CACHE_HOME",
}

PLAYWRIGHT_CONFIG = r"""import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: process.env.FACTORY26_PUBLIC_TEST_DIR,
  timeout: Number(process.env.FACTORY26_PUBLIC_TEST_TIMEOUT || 30000),
  expect: { timeout: Number(process.env.FACTORY26_PUBLIC_EXPECT_TIMEOUT || 5000) },
  fullyParallel: process.env.FACTORY26_PUBLIC_FULLY_PARALLEL === '1',
  workers: Number(process.env.FACTORY26_PUBLIC_WORKERS || 4),
  retries: 0,
  reporter: 'json',
  use: {
    baseURL: process.env.E2E_BASE_URL,
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _evaluation_environment(**extra: str) -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in EVALUATION_ENVIRONMENT_KEYS
    }
    environment.update(
        {
            "CI": "1",
            "FORCE_COLOR": "0",
            "NO_COLOR": "1",
            "NPM_CONFIG_IGNORE_SCRIPTS": "true",
            "npm_config_ignore_scripts": "true",
            **extra,
        }
    )
    return environment


def _backend_environment(
    port: int, fixture_environment: dict[str, str]
) -> dict[str, str]:
    """Expose fixtures to the app without evaluator paths or control flags."""

    environment = _evaluation_environment(PORT=str(port), HOST="127.0.0.1")
    environment.update(fixture_environment)
    return environment


def _playwright_runtime_contract(cache_root: Path) -> dict[str, Any]:
    package_path = (
        cache_root / "node_modules" / "@playwright" / "test" / "package.json"
    )
    cli_path = cache_root / "node_modules" / "@playwright" / "test" / "cli.js"
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Playwright package metadata is unreadable") from exc
    if package.get("version") != PLAYWRIGHT_VERSION:
        raise ValueError("Playwright runtime version is not pinned")
    if not cli_path.is_file() or cli_path.is_symlink():
        raise ValueError("Playwright CLI is missing or unsafe")
    cli_sha256 = sha256_file(cli_path)
    if cli_sha256 != PLAYWRIGHT_CLI_SHA256:
        raise ValueError("Playwright CLI hash differs from the pinned runtime")

    entries: list[dict[str, Any]] = []
    for relative_root in PLAYWRIGHT_RUNTIME_ROOTS:
        root = cache_root / relative_root
        if not root.is_dir():
            raise ValueError(f"Playwright runtime package is missing: {relative_root}")
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"Playwright runtime contains a symlink: {path}")
            if path.is_file():
                entries.append(
                    {
                        "path": path.relative_to(cache_root).as_posix(),
                        "bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                )
    runtime_sha256 = hashlib.sha256(
        json.dumps(
            entries,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if (
        len(entries) != PLAYWRIGHT_RUNTIME_FILE_COUNT
        or runtime_sha256 != PLAYWRIGHT_RUNTIME_SHA256
    ):
        raise ValueError("Playwright runtime tree differs from the pinned release")
    return {
        "version": PLAYWRIGHT_VERSION,
        "cli_sha256": cli_sha256,
        "runtime_file_count": len(entries),
        "runtime_sha256": runtime_sha256,
    }


def _reserve_run_label(result_root: Path, label: str) -> None:
    suffixes = (
        "feedback.json",
        "playwright.json",
        "playwright.stderr.log",
        "backend.log",
    )
    collisions = [
        result_root / f"{label}.{suffix}"
        for suffix in suffixes
        if (result_root / f"{label}.{suffix}").exists()
    ]
    if collisions:
        names = ", ".join(path.name for path in collisions)
        raise FileExistsError(
            f"public evaluation label is immutable and already exists: {names}"
        )


def ensure_playwright(cache_root: Path, *, install_browser: bool = False) -> Path:
    cache_root.mkdir(parents=True, exist_ok=True)
    package_path = cache_root / "package.json"
    config_path = cache_root / "playwright.config.mjs"
    _write(package_path, json.dumps(PLAYWRIGHT_PACKAGE, indent=2) + "\n")
    _write(config_path, PLAYWRIGHT_CONFIG)
    cli = cache_root / "node_modules" / "@playwright" / "test" / "cli.js"
    try:
        _playwright_runtime_contract(cache_root)
    except ValueError:
        completed = subprocess.run(
            ["npm", "install", "--no-audit", "--no-fund", "--ignore-scripts"],
            cwd=cache_root,
            env=_evaluation_environment(),
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Playwright npm install failed: "
                + (completed.stderr or completed.stdout)[-3000:]
            )
        _playwright_runtime_contract(cache_root)
    if install_browser:
        completed = subprocess.run(
            ["node", str(cli), "install", "chromium"],
            cwd=cache_root,
            env=_evaluation_environment(),
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Playwright Chromium install failed: "
                + (completed.stderr or completed.stdout)[-3000:]
            )
    return cli


def _wait_ready(port: int, process: subprocess.Popen, timeout: int = 30) -> None:
    deadline = time.monotonic() + timeout
    last_error = "not ready"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"generated backend exited with code {process.returncode}"
            )
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/health", timeout=2
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if response.status == 200 and payload.get("ready") is True:
                    return
                last_error = repr(payload)
        except (OSError, ValueError, urllib.error.URLError) as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(f"generated backend did not become ready: {last_error}")


def _stop(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def run_public_evaluation(
    task_id: str,
    project_dir: Path,
    cache_root: Path,
    *,
    port: int,
    workers: int = 4,
    timeout_ms: int = 30_000,
    expect_timeout_ms: int = 5_000,
    install_browser: bool = False,
    grep: str | None = None,
    fixture_profile: str = "baseline",
    fully_parallel: bool | None = None,
    run_label: str | None = None,
) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    cache_root = cache_root.resolve()
    trace = ProductionTrace(project_dir / ".arc" / "production-trace.jsonl")
    verify_run_envelope(project_dir)
    task_root = cache_root / task_id
    tests_dir = task_root / "tests"
    if not tests_dir.is_dir():
        trace.record(
            "public_evaluation_failed",
            task_id=task_id,
            stage="task_sync_preflight",
            error="public task is not synchronized",
        )
        raise FileNotFoundError(f"public task is not synchronized: {tests_dir}")
    task_bundle_before = public_task_bundle_manifest(task_root)
    if task_bundle_before.get("task_id") != task_id:
        raise ValueError("public task id does not match its synchronized manifest")
    if task_id not in PUBLIC_PLAYWRIGHT_INVENTORY_SHA256:
        raise ValueError(f"no locked Playwright contract for public task: {task_id}")
    expected_test_count = int(task_bundle_before.get("expected_test_count") or 0)
    if expected_test_count != PUBLIC_TEST_COUNTS[task_id]:
        raise ValueError("public task test count differs from the locked contract")
    expected_test_files = {
        str(item.get("path") or "")
        for item in (task_bundle_before.get("tests") or {}).get("files") or []
        if isinstance(item, dict) and str(item.get("path") or "").endswith(".spec.ts")
    }
    application_source_before = application_source_manifest(project_dir)
    check_results = run_full_checks(project_dir, port + 1)
    broken = failures(check_results)
    if broken:
        trace.record(
            "public_evaluation_failed",
            task_id=task_id,
            stage="local_preflight",
            checks=[item.as_dict() for item in check_results],
        )
        raise RuntimeError(
            "generated project failed local checks: "
            + "; ".join(item.summary for item in broken)
        )

    playwright = ensure_playwright(cache_root, install_browser=install_browser)
    playwright_runtime = _playwright_runtime_contract(cache_root)
    result_root = project_dir / ".arc" / "public-eval"
    result_root.mkdir(parents=True, exist_ok=True)
    harness_report_path = project_dir / ".arc" / "harness-report.json"
    harness_report = json.loads(harness_report_path.read_text(encoding="utf-8"))
    source_run_id = str(harness_report.get("run_id") or "")
    label = run_label or (
        task_id if fixture_profile == "baseline" else f"{task_id}.{fixture_profile}"
    )
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", label):
        raise ValueError(f"unsafe run label: {label!r}")
    _reserve_run_label(result_root, label)
    backend_log_path = result_root / f"{label}.backend.log"
    fully_parallel_value = fully_parallel if fully_parallel is not None else True
    environment = _evaluation_environment(
        PORT=str(port),
        E2E_BASE_URL=f"http://127.0.0.1:{port}",
        TARGET_URL=f"http://127.0.0.1:{port}",
        FACTORY26_PUBLIC_TEST_DIR=str(tests_dir),
        FACTORY26_PUBLIC_TEST_TIMEOUT=str(timeout_ms),
        FACTORY26_PUBLIC_EXPECT_TIMEOUT=str(expect_timeout_ms),
        FACTORY26_PUBLIC_WORKERS=str(workers),
        FACTORY26_PUBLIC_FULLY_PARALLEL="1"
        if fully_parallel_value
        else "0",
    )
    fixture_environment = public_fixture_environment(
        task_id, environment["E2E_BASE_URL"], fixture_profile
    )
    environment.update(fixture_environment)
    backend_environment = _backend_environment(port, fixture_environment)
    fixture_contract = public_fixture_environment(
        task_id, "http://127.0.0.1:<PORT>", fixture_profile
    )
    fixture_contract_sha256 = hashlib.sha256(
        json.dumps(
            fixture_contract,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    trace.record(
        "public_evaluation_started",
        source_run_id=source_run_id,
        task_id=task_id,
        run_label=label,
        fixture_profile=fixture_profile,
        workers=workers,
        fully_parallel=environment["FACTORY26_PUBLIC_FULLY_PARALLEL"] == "1",
        timeout_ms=timeout_ms,
        expect_timeout_ms=expect_timeout_ms,
        filtered=grep is not None,
        prompt_invocations=0,
        agent_iterations=0,
        manual_interventions=0,
        tool="playwright.test",
        playwright_runtime=playwright_runtime,
        fixture_contract_sha256=fixture_contract_sha256,
    )
    with backend_log_path.open("w", encoding="utf-8") as backend_log:
        process = subprocess.Popen(
            ["npm", "start"],
            cwd=project_dir / "backend",
            env=backend_environment,
            stdout=backend_log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            _wait_ready(port, process)
            started = time.monotonic()
            command = [
                "node",
                str(playwright),
                "test",
                "--config",
                str(cache_root / "playwright.config.mjs"),
            ]
            if grep:
                command.extend(["--grep", grep])
            completed = subprocess.run(
                command,
                cwd=cache_root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=max(120, timeout_ms * 4 // 1000),
                check=False,
            )
            duration = time.monotonic() - started
        finally:
            _stop(process)

    try:
        runtime_after = _playwright_runtime_contract(cache_root)
    except ValueError as exc:
        trace.record(
            "public_evaluation_failed",
            task_id=task_id,
            run_label=label,
            stage="playwright_runtime_mutated",
            error=str(exc),
        )
        raise RuntimeError("Playwright runtime changed during evaluation") from exc
    if runtime_after != playwright_runtime:
        raise RuntimeError("Playwright runtime identity changed during evaluation")

    report_path = result_root / f"{label}.playwright.json"
    stderr_path = result_root / f"{label}.playwright.stderr.log"
    _write(report_path, completed.stdout)
    _write(stderr_path, completed.stderr)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        trace.record(
            "public_evaluation_failed",
            task_id=task_id,
            run_label=label,
            stage="playwright_report_parse",
            exit_code=completed.returncode,
        )
        raise RuntimeError(
            f"Playwright did not produce JSON: {completed.stderr[-2000:]}"
        ) from exc
    try:
        report_contract = validate_playwright_report(
            payload,
            expected_test_files=expected_test_files,
            expected_test_count=expected_test_count,
            expected_inventory_sha256=PUBLIC_PLAYWRIGHT_INVENTORY_SHA256[task_id],
            expected_workers=workers,
            expected_fully_parallel=fully_parallel_value,
        )
    except ValueError as exc:
        trace.record(
            "public_evaluation_failed",
            task_id=task_id,
            run_label=label,
            stage="playwright_report_contract",
            error=str(exc),
        )
        raise RuntimeError(f"Playwright report contract failed: {exc}") from exc
    stats = payload.get("stats") or {}
    failed = parse_playwright_json(payload)
    application_source_after = application_source_manifest(project_dir)
    task_bundle_after = public_task_bundle_manifest(task_root)
    if application_source_after != application_source_before:
        trace.record(
            "public_evaluation_failed",
            task_id=task_id,
            run_label=label,
            stage="application_source_mutated",
            application_source_before=application_source_before["sha256"],
            application_source_after=application_source_after["sha256"],
        )
        raise RuntimeError("public evaluation mutated the generated application source")
    if task_bundle_after != task_bundle_before:
        trace.record(
            "public_evaluation_failed",
            task_id=task_id,
            run_label=label,
            stage="test_bundle_mutated",
            test_bundle_before=task_bundle_before["tests"]["sha256"],
            test_bundle_after=task_bundle_after["tests"]["sha256"],
        )
        raise RuntimeError("public evaluation mutated the synchronized test bundle")
    impact = ChangeImpactGraph(project_dir / ".arc" / "change-impact.json")
    packets = repair_packets(failed, impact)
    feedback_payload = {
        "version": 2,
        "source_run_id": source_run_id,
        "task_id": task_id,
        "run_label": label,
        "fixture_profile": fixture_profile,
        "fully_parallel": environment["FACTORY26_PUBLIC_FULLY_PARALLEL"] == "1",
        "workers": workers,
        "grep": grep,
        "exit_code": completed.returncode,
        "duration_seconds": round(duration, 3),
        "stats": stats,
        "failure_count": len(failed),
        "repair_packets": packets,
        "application_source_sha256": application_source_before["sha256"],
        "application_source_file_count": application_source_before["file_count"],
        "test_bundle_sha256": task_bundle_before["tests"]["sha256"],
        "test_bundle_file_count": task_bundle_before["tests"]["file_count"],
        "public_task_manifest_sha256": task_bundle_before[
            "task_manifest_sha256"
        ],
        "requirements_sha256": task_bundle_before["requirements_sha256"],
        "playwright_report_sha256": sha256_file(report_path),
        "playwright_report_contract": report_contract,
        "playwright_runtime": playwright_runtime,
        "fixture_contract_sha256": fixture_contract_sha256,
    }
    feedback_path = result_root / f"{label}.feedback.json"
    _write(
        feedback_path, json.dumps(feedback_payload, ensure_ascii=False, indent=2) + "\n"
    )
    trace.record(
        "public_evaluation_completed",
        task_id=task_id,
        run_label=label,
        fixture_profile=fixture_profile,
        workers=workers,
        fully_parallel=feedback_payload["fully_parallel"],
        exit_code=completed.returncode,
        duration_seconds=feedback_payload["duration_seconds"],
        stats=stats,
        failure_count=len(failed),
        repair_packet_count=len(packets),
        evidence_file=f".arc/public-eval/{label}.feedback.json",
        evidence_sha256=hashlib.sha256(feedback_path.read_bytes()).hexdigest(),
        playwright_report_sha256=feedback_payload["playwright_report_sha256"],
        application_source_sha256=feedback_payload["application_source_sha256"],
        test_bundle_sha256=feedback_payload["test_bundle_sha256"],
        public_task_manifest_sha256=feedback_payload[
            "public_task_manifest_sha256"
        ],
        playwright_inventory_sha256=report_contract["inventory_sha256"],
        playwright_report_contract=report_contract,
        playwright_runtime=playwright_runtime,
        fixture_contract_sha256=fixture_contract_sha256,
    )
    write_run_envelope(project_dir)
    if completed.returncode != 0 or failed:
        counterexample_path, counterexample = record_counterexample(
            project_dir,
            feedback=feedback_payload,
            repair_packets=packets,
        )
        counterexample_sha256 = sha256_file(counterexample_path)
        trace.record(
            "counterexample_observed",
            run_label=label,
            counterexample_sha256=counterexample_sha256,
            failure_count=counterexample["failure_count"],
            cluster_count=counterexample["cluster_count"],
            prompt_invocations=0,
            agent_iterations=0,
            manual_interventions=0,
        )
        write_run_envelope(project_dir)
    else:
        forge_capability_capsule(project_dir)
    return feedback_payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a synchronized public ARC task against a generated project"
    )
    parser.add_argument("task_id")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--cache", type=Path, default=Path(".cache/public-tasks"))
    parser.add_argument("--port", type=int, default=3401)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=30_000)
    parser.add_argument("--expect-timeout", type=int, default=5_000)
    parser.add_argument("--install-browser", action="store_true")
    parser.add_argument(
        "--grep", help="Only run tests whose title matches this regular expression"
    )
    parser.add_argument(
        "--fixture-profile",
        choices=("baseline", "adversarial"),
        default="baseline",
        help="Use the baseline fixtures or a deterministic renamed/mutated GitHub world",
    )
    parser.add_argument(
        "--fully-parallel",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override task-specific Playwright intra-file parallelism",
    )
    parser.add_argument(
        "--run-label", help="Safe filename label for retaining repeated evaluation runs"
    )
    parser.add_argument(
        "--strict-exit",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Return non-zero when the public test command fails (default: enabled)",
    )
    args = parser.parse_args()
    result = run_public_evaluation(
        args.task_id,
        args.project_dir,
        args.cache,
        port=args.port,
        workers=args.workers,
        timeout_ms=args.timeout,
        expect_timeout_ms=args.expect_timeout,
        install_browser=args.install_browser,
        grep=args.grep,
        fixture_profile=args.fixture_profile,
        fully_parallel=args.fully_parallel,
        run_label=args.run_label,
    )
    stats = result["stats"]
    print(
        f"{args.task_id}: expected={stats.get('expected', 0)} "
        f"unexpected={stats.get('unexpected', 0)} skipped={stats.get('skipped', 0)} "
        f"duration={result['duration_seconds']}s"
    )
    return 1 if args.strict_exit and result["exit_code"] != 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
