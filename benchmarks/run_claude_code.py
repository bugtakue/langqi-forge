from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = Path(__file__).with_name("claude_code_prompt.txt")
ALLOWED_CLAUDE_TOOLS = frozenset({"Bash", "Edit", "Glob", "Grep", "Read", "Write"})


def tool_names(value: object) -> list[str]:
    names: list[str] = []
    if isinstance(value, dict):
        if value.get("type") == "tool_use" and isinstance(value.get("name"), str):
            names.append(value["name"])
        for nested in value.values():
            names.extend(tool_names(nested))
    elif isinstance(value, list):
        for nested in value:
            names.extend(tool_names(nested))
    return names


def protocol_violations(row: dict) -> list[str]:
    violations: list[str] = []
    event_type = str(row.get("type") or "unknown").lower()
    if "web_search" in event_type or "mcp" in event_type:
        violations.append(f"forbidden_event:{event_type}")
    for name in tool_names(row):
        if name not in ALLOWED_CLAUDE_TOOLS:
            violations.append(f"forbidden_tool:{name}")
    return violations


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one immutable, fixed-budget Claude Code Factory26 build",
    )
    parser.add_argument("domain", choices=("github", "sheet"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--claude", default=shutil.which("claude") or "claude")
    parser.add_argument("--model", default="sonnet")
    parser.add_argument(
        "--effort", choices=("low", "medium", "high", "xhigh", "max"), default="high"
    )
    parser.add_argument("--max-budget-usd", type=float, default=5.0)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    return parser.parse_args()


def ensure_fresh_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.exists():
        if not resolved.is_dir() or any(resolved.iterdir()):
            raise ValueError(
                f"output directory must not exist or must be empty: {resolved}"
            )
    else:
        resolved.mkdir(parents=True)
    return resolved


def command_version(command: str) -> str:
    completed = subprocess.run(
        [command, "--version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return (completed.stdout or completed.stderr).strip()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repository_state() -> dict[str, str | bool]:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    ).stdout
    return {"revision": revision, "worktree_clean": not bool(status.strip())}


def requirement_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(entry for entry in root.rglob("*") if entry.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def trace_metrics(path: Path) -> dict:
    final: dict = {}
    malformed_rows = 0
    event_count = 0
    observed_tools: dict[str, int] = {}
    violations: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event_count += 1
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            malformed_rows += 1
            continue
        for name in tool_names(row):
            observed_tools[name] = observed_tools.get(name, 0) + 1
        violations.extend(protocol_violations(row))
        if row.get("type") == "result":
            final = row
    return {
        "event_count": event_count,
        "malformed_rows": malformed_rows,
        "observed_tools": observed_tools,
        "protocol_violations": sorted(set(violations)),
        "result_subtype": final.get("subtype", "unknown"),
        "is_error": final.get("is_error", "unknown"),
        "api_error_status": final.get("api_error_status", "unknown"),
        "terminal_reason": final.get("terminal_reason", "unknown"),
        "total_cost_usd": final.get("total_cost_usd", "unknown"),
        "num_turns": final.get("num_turns", "unknown"),
        "duration_api_ms": final.get("duration_api_ms", "unknown"),
        "usage": final.get("usage", "unknown"),
    }


def run() -> int:
    args = parse_args()
    if args.max_budget_usd <= 0 or args.timeout_seconds <= 0:
        raise ValueError("budget and timeout must be positive")
    output = ensure_fresh_output(args.output_dir)
    executable = shutil.which(args.claude)
    if not executable:
        raise FileNotFoundError(f"Claude Code executable not found: {args.claude}")
    harness_state = repository_state()
    source_requirements = (
        ROOT / ".cache" / "public-tasks" / args.domain / "requirements"
    )
    if not source_requirements.is_dir():
        raise FileNotFoundError(
            f"public requirements are missing; run public_tasks first: {source_requirements}",
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

    trace_path = output / "claude-trace.jsonl"
    stderr_path = output / "claude-stderr.log"
    metadata_path = output / "benchmark-metadata.json"
    invocation = [
        executable,
        "--print",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        args.model,
        "--effort",
        args.effort,
        "--max-budget-usd",
        str(args.max_budget_usd),
        "--permission-mode",
        "bypassPermissions",
        "--allow-dangerously-skip-permissions",
        "--no-session-persistence",
        "--no-chrome",
        "--disable-slash-commands",
        "--setting-sources",
        "",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--tools",
        "Read,Glob,Grep,Write,Edit,Bash",
    ]
    environment = dict(os.environ)
    for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "DASHSCOPE_API_KEY"):
        environment.pop(name, None)
    started_at = datetime.now(UTC).isoformat()
    started = time.monotonic()
    status = "running"
    returncode: int | None = None
    with trace_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
        "w",
        encoding="utf-8",
    ) as stderr:
        process = subprocess.Popen(
            invocation,
            cwd=workspace,
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

    metrics = trace_metrics(trace_path)
    all_violations = list(metrics["protocol_violations"])
    if metrics["malformed_rows"]:
        all_violations.append("malformed_jsonl_event")
    all_violations = sorted(set(all_violations))
    if all_violations:
        status = "protocol_violation"

    metadata = {
        "schema": "langqi-blank-workspace-agent-v2",
        "agent": "claude-code",
        "status": status,
        "returncode": returncode,
        "domain": args.domain,
        "started_at": started_at,
        "duration_seconds": round(time.monotonic() - started, 3),
        "timeout_seconds": args.timeout_seconds,
        "model": args.model,
        "effort": args.effort,
        "max_budget_usd": args.max_budget_usd,
        "claude_version": command_version(executable),
        "executable_path": str(Path(executable).resolve()),
        "executable_sha256": file_sha256(Path(executable).resolve()),
        "harness": harness_state,
        "invocation": invocation,
        "tool_policy": {
            "allowed": sorted(ALLOWED_CLAUDE_TOOLS),
            "forbidden": ["network search", "MCP", "plugins", "skills", "Chrome"],
            "enforcement": "CLI allowlist plus complete stream-JSON audit",
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
