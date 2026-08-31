from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .checks import failures, run_full_checks
from .feedback import parse_playwright_json, repair_packets
from .impact import ChangeImpactGraph
from .public_fixtures import public_fixture_environment


PLAYWRIGHT_PACKAGE = {
    "name": "factory26-public-eval-cache",
    "private": True,
    "version": "0.0.0",
    "type": "module",
    "devDependencies": {"@playwright/test": "^1.54.0"},
}

PLAYWRIGHT_CONFIG = r'''import { defineConfig, devices } from '@playwright/test';

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
'''


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def ensure_playwright(cache_root: Path, *, install_browser: bool = False) -> Path:
    cache_root.mkdir(parents=True, exist_ok=True)
    package_path = cache_root / "package.json"
    config_path = cache_root / "playwright.config.mjs"
    if not package_path.is_file():
        _write(package_path, json.dumps(PLAYWRIGHT_PACKAGE, indent=2) + "\n")
    _write(config_path, PLAYWRIGHT_CONFIG)
    binary = cache_root / "node_modules" / ".bin" / "playwright"
    if not binary.is_file():
        completed = subprocess.run(
            ["npm", "install", "--no-audit", "--no-fund"],
            cwd=cache_root,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("Playwright npm install failed: " + (completed.stderr or completed.stdout)[-3000:])
    if install_browser:
        completed = subprocess.run(
            [str(binary), "install", "chromium"],
            cwd=cache_root,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("Playwright Chromium install failed: " + (completed.stderr or completed.stdout)[-3000:])
    return binary


def _wait_ready(port: int, process: subprocess.Popen, timeout: int = 30) -> None:
    deadline = time.monotonic() + timeout
    last_error = "not ready"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"generated backend exited with code {process.returncode}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as response:
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
    tests_dir = cache_root / task_id / "tests"
    if not tests_dir.is_dir():
        raise FileNotFoundError(f"public task is not synchronized: {tests_dir}")
    check_results = run_full_checks(project_dir, port + 1)
    broken = failures(check_results)
    if broken:
        raise RuntimeError("generated project failed local checks: " + "; ".join(item.summary for item in broken))

    playwright = ensure_playwright(cache_root, install_browser=install_browser)
    result_root = project_dir / ".arc" / "public-eval"
    result_root.mkdir(parents=True, exist_ok=True)
    label = run_label or (task_id if fixture_profile == "baseline" else f"{task_id}.{fixture_profile}")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", label):
        raise ValueError(f"unsafe run label: {label!r}")
    backend_log_path = result_root / f"{label}.backend.log"
    environment = dict(
        os.environ,
        PORT=str(port),
        E2E_BASE_URL=f"http://127.0.0.1:{port}",
        TARGET_URL=f"http://127.0.0.1:{port}",
        FACTORY26_PUBLIC_TEST_DIR=str(tests_dir),
        FACTORY26_PUBLIC_TEST_TIMEOUT=str(timeout_ms),
        FACTORY26_PUBLIC_EXPECT_TIMEOUT=str(expect_timeout_ms),
        FACTORY26_PUBLIC_WORKERS=str(workers),
        FACTORY26_PUBLIC_FULLY_PARALLEL="1"
        if (fully_parallel if fully_parallel is not None else True)
        else "0",
    )
    for name, value in public_fixture_environment(
        task_id, environment["E2E_BASE_URL"], fixture_profile
    ).items():
        environment.setdefault(name, value)
    with backend_log_path.open("w", encoding="utf-8") as backend_log:
        process = subprocess.Popen(
            ["npm", "start"],
            cwd=project_dir / "backend",
            env=environment,
            stdout=backend_log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            _wait_ready(port, process)
            started = time.monotonic()
            command = [str(playwright), "test", "--config", str(cache_root / "playwright.config.mjs")]
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

    report_path = result_root / f"{label}.playwright.json"
    stderr_path = result_root / f"{label}.playwright.stderr.log"
    _write(report_path, completed.stdout)
    _write(stderr_path, completed.stderr)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Playwright did not produce JSON: {completed.stderr[-2000:]}") from exc
    stats = payload.get("stats") or {}
    failed = parse_playwright_json(payload)
    impact = ChangeImpactGraph(project_dir / ".arc" / "change-impact.json")
    packets = repair_packets(failed, impact)
    feedback_payload = {
        "version": 1,
        "task_id": task_id,
        "run_label": label,
        "fixture_profile": fixture_profile,
        "fully_parallel": environment["FACTORY26_PUBLIC_FULLY_PARALLEL"] == "1",
        "grep": grep,
        "exit_code": completed.returncode,
        "duration_seconds": round(duration, 3),
        "stats": stats,
        "failure_count": len(failed),
        "repair_packets": packets,
    }
    _write(
        result_root / f"{label}.feedback.json",
        json.dumps(feedback_payload, ensure_ascii=False, indent=2) + "\n",
    )
    return feedback_payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a synchronized public ARC task against a generated project")
    parser.add_argument("task_id")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--cache", type=Path, default=Path(".cache/public-tasks"))
    parser.add_argument("--port", type=int, default=3401)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=30_000)
    parser.add_argument("--expect-timeout", type=int, default=5_000)
    parser.add_argument("--install-browser", action="store_true")
    parser.add_argument("--grep", help="Only run tests whose title matches this regular expression")
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
    parser.add_argument("--run-label", help="Safe filename label for retaining repeated evaluation runs")
    parser.add_argument("--strict-exit", action="store_true")
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
