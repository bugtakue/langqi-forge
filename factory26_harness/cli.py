from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from arcbench_agent_runtime import AgentRuntime

from .agent import CodingAgent
from .checks import CheckResult, failures, run_full_checks
from .impact import ChangeImpactGraph
from .model import OpenAIChatClient
from .requirements import batches, detect_domain, flatten_atomic, load_requirement_tree, plan_payload
from .scaffold import scaffold_workspace
from .trace import ProductionTrace
from .workspace_tools import WorkspaceTools


def log(message: str) -> None:
    print(message, flush=True)
    print(message, file=sys.stderr, flush=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Low-token Factory26 agent bundle for ARC-Bench")
    parser.add_argument(
        "requirement_path",
        nargs="?",
        default=os.environ.get("ARCBENCH_TASK_DIR", "/workspace/task"),
    )
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--type", "--app-type", dest="app_type", default="web")
    parser.add_argument(
        "--web-port",
        type=int,
        default=int(os.environ.get("ARCBENCH_WEB_PORT", os.environ.get("ARC_WEB_PORT", "3000"))),
    )
    parser.add_argument("--smoke-port", type=int, default=int(os.environ.get("FACTORY26_SMOKE_PORT", "3100")))
    parser.add_argument("--batch-size", type=int, default=int(os.environ.get("FACTORY26_BATCH_SIZE", "3")))
    parser.add_argument("--max-agent-turns", type=int, default=int(os.environ.get("FACTORY26_MAX_AGENT_TURNS", "14")))
    parser.add_argument("--repair-rounds", type=int, default=int(os.environ.get("FACTORY26_REPAIR_ROUNDS", "2")))
    parser.add_argument("--dry-run", action="store_true", help="Build and validate the deterministic baseline without a model")
    parser.add_argument("--strict-exit", action="store_true", help="Return non-zero for local validation failures")
    return parser.parse_args()


def _output_dir(args: argparse.Namespace) -> Path:
    if args.output_dir:
        return Path(args.output_dir).expanduser().resolve()
    injected = os.environ.get("ARCBENCH_TEMPLATE_DIR", "").strip()
    if injected:
        return Path(injected).expanduser().resolve()
    return (Path.cwd() / "workspace" / f"run-{time.strftime('%Y%m%d-%H%M%S')}").resolve()


def _safe_smoke_port(smoke_port: int, grading_port: int) -> int:
    return smoke_port + 1 if smoke_port == grading_port else smoke_port


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _failure_text(results: list[CheckResult]) -> str:
    return "\n\n".join(f"[{result.name}] {result.summary}" for result in failures(results))


def _record_file_interfaces(runtime: AgentRuntime, requirement_ids: list[str], files: tuple[str, ...]) -> None:
    for file_path in files:
        interface_id = "file-" + hashlib.sha256(file_path.encode("utf-8")).hexdigest()[:16]
        current = runtime.traceability.get_interface(interface_id) or {}
        req_ids = sorted({*current.get("req_ids", []), *requirement_ids})
        runtime.traceability.upsert_interface(
            interface_id=interface_id,
            req_ids=req_ids,
            type="source_file",
            content="Observed implementation file for: " + ", ".join(req_ids),
            file_path=file_path,
            implemented=True,
        )


def _report(
    *,
    started: float,
    nodes: list,
    checks: list[CheckResult],
    model: OpenAIChatClient | None,
    agent_failures: list[str],
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "version": 1,
        "strategy": "deterministic-foundation-plus-targeted-model-repair",
        "duration_seconds": round(time.monotonic() - started, 3),
        "requirement_count": len(nodes),
        "dry_run": dry_run,
        "agent_failures": agent_failures,
        "checks": [result.as_dict() for result in checks],
        "all_local_checks_passed": all(result.passed for result in checks),
        "model_usage": {
            "prompt_tokens": model.total_prompt_tokens if model else 0,
            "completion_tokens": model.total_completion_tokens if model else 0,
        },
        "claim_boundary": "Local checks prove packaging/build/startup only; hidden GUI score is unknown until ARC-Bench evaluates it.",
    }


def main() -> int:
    args = _parse_args()
    if args.app_type != "web":
        raise SystemExit("this first harness version supports --type web only")
    started = time.monotonic()
    output_dir = _output_dir(args)
    output_dir.mkdir(parents=True, exist_ok=True)
    requirement_path = Path(args.requirement_path).expanduser().resolve()
    smoke_port = _safe_smoke_port(args.smoke_port, args.web_port)

    log(f"[env] requirement_path={requirement_path}")
    log(f"[env] output_dir={output_dir}")
    log(f"[env] model={os.environ.get('MODEL', '<unset>')}")
    log(f"[env] model_endpoint={'set' if os.environ.get('OPENAI_BASE_URL') else 'unset'}")
    log(f"[env] api_key={'set' if os.environ.get('OPENAI_API_KEY') else 'unset'}")
    log(f"[env] grading_port={args.web_port} smoke_port={smoke_port}")

    runtime = AgentRuntime.from_env(project_dir=str(output_dir))
    trace = ProductionTrace(output_dir / ".arc" / "production-trace.jsonl")
    impact = ChangeImpactGraph(output_dir / ".arc" / "change-impact.json")
    events = runtime.events
    events.mark_run_started("factory26 low-token harness started")
    trace.record(
        "run_started",
        requirement_path=str(requirement_path),
        output_dir=str(output_dir),
        dry_run=args.dry_run,
        manual_interventions=0,
    )

    model: OpenAIChatClient | None = None
    checks: list[CheckResult] = []
    nodes = []
    agent_failures: list[str] = []
    try:
        tree = load_requirement_tree(requirement_path)
        nodes = flatten_atomic(tree)
        domain = detect_domain(tree)
        runtime.traceability.store_requirement_tree(tree)
        plan = plan_payload(nodes, args.batch_size)
        plan["detected_domain"] = domain
        _write_json(output_dir / ".arc" / "compiled-plan.json", plan)
        trace.record("requirements_compiled", plan=plan)

        created = scaffold_workspace(output_dir, domain=domain)
        impact.record_requirement_files(("__foundation__",), created)
        trace.record("deterministic_scaffold", created_files=created)
        runtime.git.ensure_repo()
        runtime.git.commit("chore: deterministic runnable application foundation")

        for node in nodes:
            events.mark_design_started(node.req_id, "compiled from ARC requirement tree")
            runtime.traceability.upsert_node_contract(
                node.req_id,
                {
                    "name": node.name,
                    "dependencies": list(node.dependencies),
                    "scenarios": list(node.scenarios),
                    "batch_strategy": "small dependency-ordered batches",
                },
            )
            for scenario_index, scenario in enumerate(node.scenarios, 1):
                local_scenario_id = str(
                    scenario.get("id") or scenario.get("scenario_id") or f"scenario-{scenario_index}"
                )
                scenario_id = f"{node.req_id}::{local_scenario_id}"
                runtime.traceability.upsert_scenario(
                    scenario_id=scenario_id,
                    req_id=node.req_id,
                    name=str(scenario.get("name") or local_scenario_id),
                    steps=[dict(step) for step in scenario.get("steps") or [] if isinstance(step, dict)],
                )
                runtime.traceability.upsert_test(
                    test_id=f"contract::{scenario_id}",
                    req_id=node.req_id,
                    type="acceptance_contract",
                    scenario_id=scenario_id,
                    passed=None,
                )
            events.mark_design_done(node.req_id, "requirement contract stored")

        if args.dry_run:
            for node in nodes:
                events.mark_implementation_started(node.req_id, "dry-run baseline")
                events.mark_implementation_done(node.req_id, "model skipped; deterministic baseline retained")
        else:
            model = OpenAIChatClient(trace)
            workspace_tools = WorkspaceTools(output_dir, trace, smoke_port)
            agent = CodingAgent(model, workspace_tools, trace, max_turns=args.max_agent_turns)
            for index, group in enumerate(batches(nodes, args.batch_size), 1):
                ids = [node.req_id for node in group]
                for node in group:
                    events.mark_implementation_started(node.req_id, f"batch {index}")
                related = impact.files_for_requirements(ids)
                log(f"[flow] implementing batch {index}: {', '.join(ids)}")
                try:
                    run = agent.implement(group, related)
                except Exception as exc:
                    run = None
                    agent_failures.extend(ids)
                    trace.record("agent_batch_failed", requirement_ids=ids, error=str(exc))
                    log(f"[flow] batch {index} failed: {exc}")
                if run is not None:
                    impact.record_requirement_files(ids, run.changed_files)
                    _record_file_interfaces(runtime, ids, run.changed_files)
                    trace.record(
                        "agent_batch_result",
                        requirement_ids=ids,
                        completed=run.completed,
                        changed_files=run.changed_files,
                        turns=run.turns,
                        summary=run.summary,
                    )
                    if run.completed:
                        runtime.git.commit(f"feat: implement requirements {', '.join(ids)}")
                    else:
                        agent_failures.extend(ids)
                for node in group:
                    if node.req_id in agent_failures:
                        events.mark_implementation_failed(node.req_id, "model batch did not complete")
                    else:
                        events.mark_implementation_done(node.req_id, f"implemented in batch {index}")

        log("[verify] running clean build and startup checks")
        checks = run_full_checks(output_dir, smoke_port)
        for result in checks:
            impact.record_check_files(result.name, result.related_files)
            trace.record("validation_result", result=result.as_dict())

        if model is not None:
            workspace_tools = WorkspaceTools(output_dir, trace, smoke_port)
            repair_agent = CodingAgent(model, workspace_tools, trace, max_turns=args.max_agent_turns)
            for repair_round in range(1, max(0, args.repair_rounds) + 1):
                broken = failures(checks)
                if not broken:
                    break
                related = sorted({path for result in broken for path in result.related_files})
                log(f"[repair] deterministic failure repair round {repair_round}")
                run = repair_agent.repair(_failure_text(checks), related)
                trace.record(
                    "repair_result",
                    round=repair_round,
                    completed=run.completed,
                    changed_files=run.changed_files,
                    turns=run.turns,
                    summary=run.summary,
                )
                runtime.git.commit(f"fix: deterministic validation repair {repair_round}")
                checks = run_full_checks(output_dir, smoke_port)
                for result in checks:
                    trace.record("validation_result", repair_round=repair_round, result=result.as_dict())

        local_passed = all(result.passed for result in checks)
        for node in nodes:
            if local_passed and node.req_id not in agent_failures:
                events.mark_test_passed(node.req_id, "packaging, build, startup and health checks passed")
            else:
                events.mark_test_failed(node.req_id, "local contract checks or implementation batch failed")
        runtime.git.commit("chore: final deterministic validation")

        report = _report(
            started=started,
            nodes=nodes,
            checks=checks,
            model=model,
            agent_failures=sorted(set(agent_failures)),
            dry_run=args.dry_run,
        )
        _write_json(output_dir / ".arc" / "harness-report.json", report)
        trace.record("run_completed", report=report)
        events.mark_run_completed(
            "local contract checks passed" if local_passed else "completed with local validation failures"
        )

        artifacts_dir = os.environ.get("ARCBENCH_ARTIFACTS_DIR", "").strip()
        if artifacts_dir:
            _write_json(Path(artifacts_dir) / "preview-ready.json", {"ready": local_passed, "reason": "harness completed"})
        log(f"[done] local checks {'passed' if local_passed else 'failed'} in {report['duration_seconds']}s")
        return 0 if local_passed or not args.strict_exit else 1
    except Exception as exc:
        trace.record("run_failed", error=str(exc))
        events.mark_run_failed(str(exc)[:1000])
        log(f"[fatal] {exc}")
        return 1 if args.strict_exit else 0


if __name__ == "__main__":
    raise SystemExit(main())
