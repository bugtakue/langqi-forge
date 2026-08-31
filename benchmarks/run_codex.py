from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

try:
    from benchmarks.run_claude_code import (
        PROMPT_PATH,
        ROOT,
        command_version,
        ensure_fresh_output,
        file_sha256,
        repository_state,
        requirement_digest,
        resolve_executable,
    )
except ModuleNotFoundError:  # Direct `python benchmarks/run_codex.py ...` execution.
    from run_claude_code import (  # type: ignore[no-redef]
        PROMPT_PATH,
        ROOT,
        command_version,
        ensure_fresh_output,
        file_sha256,
        repository_state,
        requirement_digest,
        resolve_executable,
    )


MIN_CODEX_CLI_VERSION = (0, 151, 0)
PINNED_CODEX = (
    ROOT
    / ".cache"
    / "benchmark-tools"
    / "codex-0.151.0"
    / "node_modules"
    / ".bin"
    / "codex"
)
CODEX_ISOLATION_CONFIG = (
    'approval_policy="never"',
    'web_search="disabled"',
    "tools.web_search=false",
    "features.apps=false",
    "apps._default.enabled=false",
    "features.plugins=false",
    "features.remote_plugin=false",
    "features.recommended_plugins=false",
    "features.multi_agent=false",
    "agents.enabled=false",
    "features.hooks=false",
    "features.skill_search=false",
    "features.browser_use=false",
    "features.browser_use_external=false",
    "features.computer_use=false",
    "features.in_app_browser=false",
    "features.image_generation=false",
    "features.view_image=false",
    "tools.view_image=false",
)
FORBIDDEN_CODEX_ITEM_MARKERS = (
    "app_tool",
    "browser",
    "collaboration",
    "computer_use",
    "connector",
    "image_generation",
    "mcp",
    "plugin",
    "skill",
    "subagent",
    "tool_suggest",
    "web_search",
)


def default_codex() -> str:
    configured = os.environ.get("LANGQI_CODEX_BIN")
    if configured:
        return configured
    if PINNED_CODEX.is_file():
        return str(PINNED_CODEX)
    return shutil.which("codex") or "codex"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one immutable, wall-clock-bounded Codex Factory26 build",
    )
    parser.add_argument("domain", choices=("github", "sheet"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--codex", default=default_codex())
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument(
        "--effort", choices=("low", "medium", "high", "xhigh"), default="high"
    )
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    return parser.parse_args()


def parse_codex_version(raw: str) -> tuple[int, int, int] | None:
    prefix = "codex-cli "
    if not raw.startswith(prefix):
        return None
    parts = raw.removeprefix(prefix).strip().split(".")
    if len(parts) < 3:
        return None
    try:
        major, minor, patch = (int(part) for part in parts[:3])
    except ValueError:
        return None
    return major, minor, patch


def validate_codex_version(raw: str) -> tuple[int, int, int]:
    parsed = parse_codex_version(raw)
    if parsed is None:
        raise ValueError(f"unrecognized Codex CLI version: {raw!r}")
    if parsed < MIN_CODEX_CLI_VERSION:
        minimum = ".".join(str(part) for part in MIN_CODEX_CLI_VERSION)
        raise ValueError(
            f"Codex CLI {minimum}+ required for the current model/tool protocol; got {raw}"
        )
    return parsed


def protocol_violations(row: dict) -> list[str]:
    event_type = str(row.get("type") or "unknown").lower()
    item = row.get("item") if isinstance(row.get("item"), dict) else {}
    item_type = str(item.get("type") or "").lower()
    violations: list[str] = []
    for marker in FORBIDDEN_CODEX_ITEM_MARKERS:
        if marker in event_type or marker in item_type:
            violations.append(f"forbidden_tool_event:{event_type}:{item_type}:{marker}")
    return violations


def trace_metrics(path: Path) -> dict:
    malformed_rows = 0
    event_count = 0
    event_types: dict[str, int] = {}
    final_usage: dict | str = "unknown"
    thread_id = "unknown"
    terminal_error: str | None = None
    violations: list[str] = []
    item_types: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event_count += 1
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            malformed_rows += 1
            continue
        event_type = str(row.get("type") or "unknown")
        event_types[event_type] = event_types.get(event_type, 0) + 1
        item = row.get("item") if isinstance(row.get("item"), dict) else {}
        item_type = str(item.get("type") or "")
        if item_type:
            item_types[item_type] = item_types.get(item_type, 0) + 1
        violations.extend(protocol_violations(row))
        if event_type == "thread.started" and row.get("thread_id"):
            thread_id = str(row["thread_id"])
        if event_type == "turn.completed" and isinstance(row.get("usage"), dict):
            final_usage = row["usage"]
        if event_type in {"error", "turn.failed"}:
            terminal_error = str(row.get("message") or row.get("error") or event_type)
    return {
        "event_count": event_count,
        "malformed_rows": malformed_rows,
        "event_types": event_types,
        "item_types": item_types,
        "thread_id": thread_id,
        "usage": final_usage,
        "terminal_error": terminal_error,
        "protocol_violations": sorted(set(violations)),
    }


def terminate_process_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)


def monitor_codex(
    process: subprocess.Popen[str],
    *,
    prompt: str,
    trace_path: Path,
    timeout_seconds: int,
) -> tuple[str, int | None, list[str]]:
    if process.stdin is None or process.stdout is None:
        raise RuntimeError("Codex process pipes were not created")
    live_violations: list[str] = []
    violation_seen = threading.Event()
    reader_error: list[str] = []

    def read_trace() -> None:
        try:
            with trace_path.open("w", encoding="utf-8") as trace:
                for line in process.stdout:
                    trace.write(line)
                    trace.flush()
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        live_violations.append("malformed_jsonl_event")
                        violation_seen.set()
                        continue
                    found = protocol_violations(row)
                    if found:
                        live_violations.extend(found)
                        violation_seen.set()
        except Exception as exc:  # pragma: no cover - defensive process boundary
            reader_error.append(f"trace_reader_error:{type(exc).__name__}:{exc}")
            violation_seen.set()

    reader = threading.Thread(target=read_trace, name="codex-trace-reader", daemon=True)
    reader.start()
    try:
        process.stdin.write(prompt)
        process.stdin.close()
    except BrokenPipeError:
        pass

    deadline = time.monotonic() + timeout_seconds
    status = "running"
    while process.poll() is None:
        if violation_seen.is_set():
            status = "protocol_violation"
            terminate_process_group(process)
            break
        if time.monotonic() >= deadline:
            status = "timeout"
            terminate_process_group(process)
            break
        time.sleep(0.05)

    try:
        returncode = process.wait(timeout=10)
    except subprocess.TimeoutExpired:  # pragma: no cover - SIGKILL should be terminal
        terminate_process_group(process)
        returncode = process.wait(timeout=10)
    reader.join(timeout=10)
    live_violations.extend(reader_error)
    if reader.is_alive():
        live_violations.append("trace_reader_did_not_finish")
    else:
        process.stdout.close()
    if live_violations:
        status = "protocol_violation"
    elif status == "running":
        status = "completed" if returncode == 0 else "failed"
    return status, returncode, sorted(set(live_violations))


def run() -> int:
    args = parse_args()
    if args.timeout_seconds <= 0:
        raise ValueError("timeout must be positive")
    executable = resolve_executable(args.codex)
    codex_version = command_version(executable)
    validate_codex_version(codex_version)
    harness_state = repository_state()
    output = ensure_fresh_output(args.output_dir)
    source_requirements = (
        ROOT / ".cache" / "public-tasks" / args.domain / "requirements"
    )
    if not source_requirements.is_dir():
        raise FileNotFoundError(
            f"public requirements are missing; run public_tasks first: {source_requirements}"
        )

    control_root = output / "control"
    requirements = control_root / "requirements"
    workspace = output / "workspace"
    control_root.mkdir()
    workspace.mkdir()
    shutil.copytree(source_requirements, requirements)
    prompt = PROMPT_PATH.read_text(encoding="utf-8").format(
        requirements_dir=requirements,
        domain=args.domain,
    )
    exact_prompt_path = control_root / "prompt.txt"
    exact_prompt_path.write_text(prompt, encoding="utf-8")
    for path in requirements.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    requirements.chmod(0o555)
    exact_prompt_path.chmod(0o444)
    control_root.chmod(0o555)

    trace_path = output / "codex-trace.jsonl"
    stderr_path = output / "codex-stderr.log"
    final_message_path = output / "codex-final-message.txt"
    metadata_path = output / "benchmark-metadata.json"
    invocation = [
        executable,
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "--json",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "--model",
        args.model,
        "--config",
        f'model_reasoning_effort="{args.effort}"',
    ]
    for setting in CODEX_ISOLATION_CONFIG:
        invocation.extend(("--config", setting))
    invocation.extend(
        (
            "--cd",
            str(workspace),
            "--output-last-message",
            str(final_message_path),
            "-",
        )
    )
    environment = dict(os.environ)
    for name in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "DASHSCOPE_API_KEY",
    ):
        environment.pop(name, None)

    started_at = datetime.now(UTC).isoformat()
    started = time.monotonic()
    live_violations: list[str] = []
    with stderr_path.open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(
            invocation,
            cwd=workspace,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        status, returncode, live_violations = monitor_codex(
            process,
            prompt=prompt,
            trace_path=trace_path,
            timeout_seconds=args.timeout_seconds,
        )

    metrics = trace_metrics(trace_path)
    all_violations = sorted(set(live_violations).union(metrics["protocol_violations"]))
    if metrics["malformed_rows"]:
        all_violations.append("malformed_jsonl_event")
    all_violations = sorted(set(all_violations))
    if all_violations:
        status = "protocol_violation"

    metadata = {
        "schema": "langqi-blank-workspace-agent-v2",
        "agent": "codex",
        "status": status,
        "returncode": returncode,
        "domain": args.domain,
        "started_at": started_at,
        "duration_seconds": round(time.monotonic() - started, 3),
        "timeout_seconds": args.timeout_seconds,
        "model": args.model,
        "effort": args.effort,
        "codex_version": codex_version,
        "executable_path": str(Path(executable).resolve()),
        "executable_sha256": file_sha256(Path(executable).resolve()),
        "harness": harness_state,
        "minimum_codex_version": ".".join(str(part) for part in MIN_CODEX_CLI_VERSION),
        "invocation": invocation,
        "tool_policy": {
            "allowed": ["shell", "file changes", "reasoning", "plan"],
            "forbidden": list(FORBIDDEN_CODEX_ITEM_MARKERS),
            "config": list(CODEX_ISOLATION_CONFIG),
            "enforcement": "environment config plus live JSONL termination",
        },
        "protocol_violations": all_violations,
        "requirements_sha256": requirement_digest(requirements),
        "requirements_path": str(requirements),
        "requirements_source": str(source_requirements),
        "workspace_path": str(workspace),
        "prompt_template_path": str(PROMPT_PATH),
        "exact_prompt_path": str(exact_prompt_path),
        "trace_path": str(trace_path),
        "stderr_path": str(stderr_path),
        "final_message_path": str(final_message_path),
        "manual_interventions": 0,
        "evaluation_run": False,
        "trace_metrics": metrics,
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metadata, ensure_ascii=False))
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(run())
