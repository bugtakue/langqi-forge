from __future__ import annotations

import json
import os
import re
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


SAFE_ENVIRONMENT_KEYS = {
    "CI",
    "COMSPEC",
    "FORCE_COLOR",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "NO_COLOR",
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "TMPDIR",
    "TZ",
}
FORBIDDEN_LIFECYCLE_SCRIPTS = {
    "install",
    "postinstall",
    "postpack",
    "postprepare",
    "preinstall",
    "prepack",
    "prepare",
    "prepublish",
    "prepublishOnly",
}
BLOCKING_DIALOG_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_$])(?:(?:window|globalThis)\s*\.\s*)?"
    r"(?:alert|confirm|prompt)\s*\("
)
INTERACTION_SOURCE_SUFFIXES = {".html", ".js", ".jsx", ".mjs", ".ts", ".tsx"}


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    summary: str
    related_files: tuple[str, ...]
    duration_seconds: float

    def as_dict(self) -> dict:
        return asdict(self)


def _safe_environment(**extra: str) -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in SAFE_ENVIRONMENT_KEYS
    }
    environment.update(
        {
            "CI": "1",
            "NPM_CONFIG_IGNORE_SCRIPTS": "true",
            "npm_config_ignore_scripts": "true",
            **extra,
        }
    )
    return environment


def _run(
    command: list[str],
    cwd: Path,
    timeout: int,
    *,
    environment: dict[str, str] | None = None,
) -> tuple[int, str, float]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=environment or _safe_environment(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        output = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
        return completed.returncode, output[-4000:], time.monotonic() - started
    except subprocess.TimeoutExpired as exc:
        output = ((exc.stdout or "") + "\n" + (exc.stderr or "")).strip()
        return (
            124,
            f"timeout after {timeout}s\n{output[-3000:]}",
            time.monotonic() - started,
        )
    except OSError as exc:
        return 127, str(exc), time.monotonic() - started


def structure_check(root: Path) -> CheckResult:
    started = time.monotonic()
    required = (
        "frontend/package.json",
        "backend/package.json",
    )
    missing = [relative for relative in required if not (root / relative).is_file()]
    summary = "structure complete" if not missing else "missing: " + ", ".join(missing)
    return CheckResult(
        "structure", not missing, summary, required, time.monotonic() - started
    )


def package_policy_check(root: Path) -> CheckResult:
    started = time.monotonic()
    manifests = (
        (root / "frontend" / "package.json", "build"),
        (root / "backend" / "package.json", "start"),
    )
    errors: list[str] = []
    related = tuple(str(path.relative_to(root)) for path, _ in manifests)
    for path, required_script in manifests:
        try:
            if path.stat().st_size > 128_000:
                errors.append(f"{path.name} exceeds 128KB")
                continue
            package = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.relative_to(root)} is invalid: {exc}")
            continue
        scripts = package.get("scripts") or {}
        if not isinstance(scripts, dict):
            errors.append(f"{path.relative_to(root)} scripts must be an object")
            continue
        if not str(scripts.get(required_script) or "").strip():
            errors.append(
                f"{path.relative_to(root)} is missing script {required_script}"
            )
        forbidden = sorted(FORBIDDEN_LIFECYCLE_SCRIPTS.intersection(scripts))
        if forbidden:
            errors.append(
                f"{path.relative_to(root)} contains forbidden lifecycle scripts: {', '.join(forbidden)}"
            )
        for section in ("dependencies", "devDependencies"):
            dependencies = package.get(section) or {}
            if not isinstance(dependencies, dict) or len(dependencies) > 200:
                errors.append(
                    f"{path.relative_to(root)} {section} must contain at most 200 entries"
                )
                continue
            for name, version in dependencies.items():
                text = str(version or "")
                if (
                    len(str(name)) > 214
                    or len(text) > 500
                    or text.startswith(("file:", "link:", "/", "../", "./"))
                    or "..\\" in text
                ):
                    errors.append(
                        f"{path.relative_to(root)} contains unsafe dependency source for {name}"
                    )
    return CheckResult(
        "package_policy",
        not errors,
        "package policy passed" if not errors else "; ".join(errors),
        related,
        time.monotonic() - started,
    )


def interaction_policy_check(root: Path) -> CheckResult:
    """Reject blocking browser dialogs that hide product feedback from the DOM."""

    started = time.monotonic()
    source_root = root / "frontend" / "src"
    related: list[str] = []
    violations: list[str] = []
    if source_root.is_dir():
        for path in sorted(source_root.rglob("*")):
            if (
                not path.is_file()
                or path.suffix.lower() not in INTERACTION_SOURCE_SUFFIXES
            ):
                continue
            relative = path.relative_to(root).as_posix()
            related.append(relative)
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                violations.append(f"{relative} is unreadable: {exc}")
                continue
            for match in BLOCKING_DIALOG_PATTERN.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                violations.append(f"{relative}:{line} uses a blocking browser dialog")
                if len(violations) >= 20:
                    break
            if len(violations) >= 20:
                break
    summary = (
        "interaction policy passed"
        if not violations
        else "; ".join(violations)
        + "; render validation and action feedback in the owning semantic DOM container"
    )
    return CheckResult(
        "interaction_policy",
        not violations,
        summary,
        tuple(related),
        time.monotonic() - started,
    )


def _npm_install(directory: Path) -> tuple[int, str, float]:
    package = json.loads((directory / "package.json").read_text(encoding="utf-8"))
    dependencies = package.get("dependencies") or {}
    dev_dependencies = package.get("devDependencies") or {}
    if not dependencies and not dev_dependencies:
        return 0, "no npm dependencies", 0.0
    return _run(
        ["npm", "install", "--ignore-scripts", "--no-audit", "--no-fund"],
        directory,
        600,
        environment=_safe_environment(),
    )


def frontend_build_check(root: Path) -> CheckResult:
    frontend = root / "frontend"
    related = ("frontend/package.json", "frontend/src", "frontend/build.mjs")
    if not (frontend / "package.json").is_file():
        return CheckResult(
            "frontend_build", False, "frontend/package.json missing", related, 0.0
        )
    install_rc, install_output, install_seconds = _npm_install(frontend)
    if install_rc != 0:
        return CheckResult(
            "frontend_build",
            False,
            f"npm install failed\n{install_output}",
            related,
            install_seconds,
        )
    rc, output, seconds = _run(
        ["npm", "run", "build"],
        frontend,
        600,
        environment=_safe_environment(),
    )
    return CheckResult(
        "frontend_build",
        rc == 0,
        "frontend build passed" if rc == 0 else f"frontend build failed\n{output}",
        related,
        install_seconds + seconds,
    )


def _wait_for_health(
    port: int, process: subprocess.Popen, timeout: int
) -> tuple[bool, str]:
    deadline = time.monotonic() + timeout
    last_error = "not ready"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False, f"backend exited with code {process.returncode}"
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/health", timeout=2
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if response.status == 200 and payload.get("ready") is True:
                    return True, "health endpoint ready"
                last_error = f"health payload was {payload!r}"
        except (OSError, ValueError, urllib.error.URLError) as exc:
            last_error = str(exc)
        time.sleep(0.25)
    return False, last_error


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def startup_check(root: Path, smoke_port: int) -> CheckResult:
    started = time.monotonic()
    backend = root / "backend"
    related = ("backend/package.json", "backend/server.mjs", "frontend/dist")
    if not (backend / "package.json").is_file():
        return CheckResult(
            "startup_health", False, "backend/package.json missing", related, 0.0
        )
    if not _port_available(smoke_port):
        return CheckResult(
            "startup_health",
            False,
            f"smoke port {smoke_port} is already occupied",
            related,
            0.0,
        )
    install_rc, install_output, _ = _npm_install(backend)
    if install_rc != 0:
        return CheckResult(
            "startup_health",
            False,
            f"backend npm install failed\n{install_output}",
            related,
            time.monotonic() - started,
        )
    environment = _safe_environment(PORT=str(smoke_port))
    process = subprocess.Popen(
        ["npm", "start"],
        cwd=backend,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        passed, summary = _wait_for_health(smoke_port, process, 30)
        if not passed and process.stdout is not None and process.poll() is not None:
            try:
                summary += "\n" + process.stdout.read()[-3000:]
            except OSError:
                pass
        return CheckResult(
            "startup_health", passed, summary, related, time.monotonic() - started
        )
    finally:
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


def run_full_checks(root: Path, smoke_port: int) -> list[CheckResult]:
    results = [structure_check(root)]
    if results[-1].passed:
        results.append(package_policy_check(root))
    if results[-1].passed:
        results.append(interaction_policy_check(root))
    if results[-1].passed:
        results.append(frontend_build_check(root))
    if results[-1].passed:
        results.append(startup_check(root, smoke_port))
    return results


def failures(results: Iterable[CheckResult]) -> list[CheckResult]:
    return [result for result in results if not result.passed]
