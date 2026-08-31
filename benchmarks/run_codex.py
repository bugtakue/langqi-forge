from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

try:
    from benchmarks.run_claude_code import (
        PROMPT_PATH,
        ROOT,
        command_version,
        ensure_fresh_output,
        requirement_digest,
    )
except ModuleNotFoundError:  # Direct `python benchmarks/run_codex.py ...` execution.
    from run_claude_code import (  # type: ignore[no-redef]
        PROMPT_PATH,
        ROOT,
        command_version,
        ensure_fresh_output,
        requirement_digest,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one immutable, wall-clock-bounded Codex Factory26 build",
    )
    parser.add_argument("domain", choices=("github", "sheet"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--codex", default=shutil.which("codex") or "codex")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument(
        "--effort", choices=("low", "medium", "high", "xhigh"), default="high"
    )
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    return parser.parse_args()


def trace_metrics(path: Path) -> dict:
    malformed_rows = 0
    event_count = 0
    event_types: dict[str, int] = {}
    final_usage: dict | str = "unknown"
    thread_id = "unknown"
    terminal_error: str | None = None
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
        "thread_id": thread_id,
        "usage": final_usage,
        "terminal_error": terminal_error,
    }


def run() -> int:
    args = parse_args()
    if args.timeout_seconds <= 0:
        raise ValueError("timeout must be positive")
    output = ensure_fresh_output(args.output_dir)
    executable = shutil.which(args.codex)
    if not executable:
        raise FileNotFoundError(f"Codex executable not found: {args.codex}")
    source_requirements = ROOT / ".cache" / "public-tasks" / args.domain / "requirements"
    if not source_requirements.is_dir():
        raise FileNotFoundError(
            f"public requirements are missing; run public_tasks first: {source_requirements}"
        )

    input_root = output / ".benchmark-input"
    requirements = input_root / "requirements"
    input_root.mkdir()
    shutil.copytree(source_requirements, requirements)
    prompt = PROMPT_PATH.read_text(encoding="utf-8").format(
        requirements_dir=requirements,
        domain=args.domain,
    )
    exact_prompt_path = input_root / "prompt.txt"
    exact_prompt_path.write_text(prompt, encoding="utf-8")
    for path in requirements.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    requirements.chmod(0o555)

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
        "--config",
        'approval_policy="never"',
        "--cd",
        str(output),
        "--output-last-message",
        str(final_message_path),
        "-",
    ]
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
    status = "running"
    returncode: int | None = None
    with trace_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr:
        process = subprocess.Popen(
            invocation,
            cwd=output,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=stdout,
            stderr=stderr,
            text=True,
            start_new_session=True,
        )
        try:
            process.communicate(input=prompt, timeout=args.timeout_seconds)
            returncode = process.returncode
            status = "completed" if returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            status = "timeout"
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=10)
            returncode = process.returncode

    metadata = {
        "schema": "langqi-blank-workspace-agent-v1",
        "agent": "codex",
        "status": status,
        "returncode": returncode,
        "domain": args.domain,
        "started_at": started_at,
        "duration_seconds": round(time.monotonic() - started, 3),
        "timeout_seconds": args.timeout_seconds,
        "model": args.model,
        "effort": args.effort,
        "codex_version": command_version(executable),
        "requirements_sha256": requirement_digest(requirements),
        "requirements_path": str(requirements),
        "requirements_source": str(source_requirements),
        "prompt_template_path": str(PROMPT_PATH),
        "exact_prompt_path": str(exact_prompt_path),
        "trace_path": str(trace_path),
        "stderr_path": str(stderr_path),
        "final_message_path": str(final_message_path),
        "manual_interventions": 0,
        "evaluation_run": False,
        "trace_metrics": trace_metrics(trace_path),
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metadata, ensure_ascii=False))
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(run())
