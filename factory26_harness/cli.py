from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from arcbench_agent_runtime import AgentRuntime

from .agent import CodingAgent
from .artifacts import application_source_manifest, write_run_envelope
from .capabilities import (
    CoverageAnalysis,
    analyze_coverage,
    generated_implementation_files,
)
from .capability_memory import match_capability_capsule, verify_capability_capsule
from .checks import CheckResult, failures, run_full_checks
from .impact import ChangeImpactGraph
from .model import OpenAIChatClient
from .planner import SpecificationPlanner
from .requirements import (
    batches,
    detect_domain,
    flatten_atomic,
    load_requirement_tree,
    plan_payload,
    requirement_source_sha256,
)
from .scaffold import scaffold_workspace
from .submission_bundle import (
    SOURCE_MANIFEST_NAME,
    require_external_output_directory,
    verify_source_manifest,
)
from .trace import ProductionTrace
from .workspace_tools import WorkspaceTools

DETERMINISTIC_DOMAINS = frozenset({"github", "sheet"})
SOURCE_ROOT = Path(__file__).resolve().parents[1]


def log(message: str) -> None:
    print(message, flush=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Low-token Factory26 agent bundle for ARC-Bench"
    )
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
        default=int(
            os.environ.get("ARCBENCH_WEB_PORT", os.environ.get("ARC_WEB_PORT", "3000"))
        ),
    )
    parser.add_argument(
        "--smoke-port",
        type=int,
        default=int(os.environ.get("FACTORY26_SMOKE_PORT", "3100")),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.environ.get("FACTORY26_BATCH_SIZE", "3")),
    )
    parser.add_argument(
        "--max-agent-turns",
        type=int,
        default=int(os.environ.get("FACTORY26_MAX_AGENT_TURNS", "14")),
    )
    parser.add_argument(
        "--repair-rounds",
        type=int,
        default=int(os.environ.get("FACTORY26_REPAIR_ROUNDS", "2")),
    )
    parser.add_argument(
        "--capability-capsule",
        action="append",
        default=[],
        help="Verified prior capability capsule to consult as provisional warm-start evidence",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and validate the deterministic baseline without a model",
    )
    parser.add_argument(
        "--strict-exit",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Return non-zero for local validation failures (default: enabled)",
    )
    return parser.parse_args()


def _output_dir(args: argparse.Namespace) -> Path:
    if args.output_dir:
        return Path(args.output_dir).expanduser().resolve()
    injected = os.environ.get("ARCBENCH_TEMPLATE_DIR", "").strip()
    if injected:
        return Path(injected).expanduser().resolve()
    return (
        Path.cwd() / "workspace" / f"run-{time.strftime('%Y%m%d-%H%M%S')}"
    ).resolve()


def _safe_smoke_port(smoke_port: int, grading_port: int) -> int:
    if not 1_024 <= smoke_port <= 65_535:
        raise ValueError("smoke port must be between 1024 and 65535")
    for offset in range(128):
        candidate = smoke_port + offset
        if candidate > 65_535:
            candidate = 1_024 + (candidate - 65_536)
        if candidate == grading_port:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", candidate))
            except OSError:
                continue
        return candidate
    raise RuntimeError("no available smoke port found in the bounded search window")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _transaction_checksum(transactions: list[dict[str, Any]]) -> str:
    encoded = json.dumps(
        {"version": 2, "transactions": transactions},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_transaction_ledger(
    path: Path, transactions: list[dict[str, Any]]
) -> None:
    _write_json(
        path,
        {
            "version": 2,
            "transactions": transactions,
            "checksum": _transaction_checksum(transactions),
        },
    )


def _recover_open_transactions(
    output_dir: Path,
    runtime: AgentRuntime,
    trace: ProductionTrace,
    run_id: str,
) -> list[dict[str, Any]]:
    ledger_path = output_dir / ".arc" / "transaction-ledger.json"
    if not ledger_path.is_file():
        return []
    try:
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("transaction ledger is unreadable; refusing unsafe recovery") from exc
    if payload.get("version") == 2 and payload.get("checksum") != _transaction_checksum(
        [dict(item) for item in payload.get("transactions") or [] if isinstance(item, dict)]
    ):
        raise RuntimeError("transaction ledger checksum is invalid; refusing unsafe recovery")
    transactions = [
        dict(item)
        for item in payload.get("transactions") or []
        if isinstance(item, dict)
    ]
    open_transactions = [item for item in transactions if item.get("status") == "open"]
    if open_transactions and not (output_dir / ".git").is_dir():
        raise RuntimeError("an open transaction exists but its git checkpoint is unavailable")
    for transaction in open_transactions:
        checkpoint = str(transaction.get("checkpoint_commit") or "")
        runtime.git.restore_paths(checkpoint, ("frontend", "backend"))
        transaction["status"] = "rolled_back_on_restart"
        transaction["recovery_run_id"] = run_id
        transaction["recovered_at"] = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
        )
        trace.record(
            "open_transaction_recovered",
            checkpoint_commit=checkpoint,
            transaction=transaction,
        )
    if open_transactions:
        _write_transaction_ledger(ledger_path, transactions)
    return transactions


def _source_identity() -> dict[str, Any]:
    manifest_path = SOURCE_ROOT / SOURCE_MANIFEST_NAME
    declared = os.environ.get("FACTORY26_SOURCE_REVISION", "").strip()
    if manifest_path.is_file():
        manifest = verify_source_manifest(SOURCE_ROOT)
        if declared and declared != manifest["source_revision"]:
            raise RuntimeError(
                "declared source revision does not match verified submission manifest"
            )
        return {
            "revision": manifest["source_revision"],
            "worktree_clean": True,
            "source": "verified-submission-manifest",
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        }
    if declared:
        return {"revision": declared, "worktree_clean": None, "source": "environment"}
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=SOURCE_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=SOURCE_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()
        return {"revision": revision, "worktree_clean": not status, "source": "git"}
    except (OSError, subprocess.SubprocessError):
        return {
            "revision": "unavailable",
            "worktree_clean": None,
            "source": "unpacked-bundle-without-source-manifest",
        }


def _failure_text(results: list[CheckResult]) -> str:
    return "\n\n".join(
        f"[{result.name}] {result.summary}" for result in failures(results)
    )


def _unexpected_transaction_paths(runtime: AgentRuntime) -> tuple[str, ...]:
    allowed_prefixes = ("frontend/", "backend/", ".arc/traceability/")
    return tuple(
        path
        for path in runtime.git.changed_paths()
        if path not in {"frontend", "backend", ".arc/traceability"}
        and not path.startswith(allowed_prefixes)
    )


def _record_file_interfaces(
    runtime: AgentRuntime, requirement_ids: list[str], files: tuple[str, ...]
) -> None:
    for file_path in files:
        interface_id = (
            "file-" + hashlib.sha256(file_path.encode("utf-8")).hexdigest()[:16]
        )
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
    domain: str,
    execution_route: str,
    agent_iterations: int,
    planner_status: str,
    planner_contract: dict[str, Any] | None,
    planner_iterations: int,
    coding_agent_iterations: int,
    requirement_sha256: str,
    run_id: str,
    source_identity: dict[str, Any],
    coverage: CoverageAnalysis | None,
    transactions: list[dict[str, Any]],
    application_source: dict[str, Any],
    capability_memory: list[dict[str, Any]],
) -> dict[str, Any]:
    current_transactions = [
        item
        for item in transactions
        if item.get("run_id") == run_id or item.get("recovery_run_id") == run_id
    ]
    return {
        "version": 2,
        "strategy": "one-planner-call-then-deterministic-kernel-or-targeted-repair",
        "run_id": run_id,
        "source_identity": source_identity,
        "duration_seconds": round(time.monotonic() - started, 3),
        "requirement_count": len(nodes),
        "requirement_sha256": requirement_sha256,
        "application_source": application_source,
        "dry_run": dry_run,
        "detected_domain": domain,
        "execution_route": execution_route,
        "agent_iterations": agent_iterations,
        "planner_status": planner_status,
        "planner_contract": planner_contract,
        "planner_iterations": planner_iterations,
        "coding_agent_iterations": coding_agent_iterations,
        "manual_interventions": 0,
        "agent_failures": agent_failures,
        "checks": [result.as_dict() for result in checks],
        "all_local_checks_passed": all(result.passed for result in checks),
        "run_completed_successfully": all(result.passed for result in checks)
        and not agent_failures,
        "behavioral_validation": {
            "state": "pending_black_box_evidence",
            "local_checks_are_behavioral_proof": False,
            "required_next_evidence": (
                "locked public Playwright evaluation"
                if domain in DETERMINISTIC_DOMAINS
                else "independent black-box acceptance contract"
            ),
        },
        "model_usage": {
            "prompt_tokens": model.total_prompt_tokens if model else 0,
            "completion_tokens": model.total_completion_tokens if model else 0,
            "request_count": model.request_count if model else 0,
            "http_attempt_count": model.http_attempt_count if model else 0,
        },
        "model_gateway": model.gateway_evidence() if model else None,
        "capability_coverage": coverage.as_dict() if coverage else None,
        "capability_memory": {
            "matched_capsules": capability_memory,
            "reuse_skipped_revalidation": False,
        },
        "transaction_safety": {
            "batch_count": len(current_transactions),
            "committed": sum(
                item.get("status") == "committed" for item in current_transactions
            ),
            "rolled_back": sum(
                str(item.get("status") or "").startswith("rolled_back")
                for item in current_transactions
            ),
            "transactions": current_transactions,
        },
        "claim_boundary": "Local checks prove packaging/build/startup only; hidden GUI score is unknown until ARC-Bench evaluates it.",
    }


def main() -> int:
    args = _parse_args()
    if args.app_type != "web":
        raise SystemExit("this first harness version supports --type web only")
    started = time.monotonic()
    output_dir = _output_dir(args)
    require_external_output_directory(SOURCE_ROOT, output_dir)
    source_identity = _source_identity()
    output_dir.mkdir(parents=True, exist_ok=True)
    requirement_path = Path(args.requirement_path).expanduser().resolve()
    smoke_port = _safe_smoke_port(args.smoke_port, args.web_port)
    run_id = os.environ.get("FACTORY26_RUN_ID", "").strip() or str(uuid.uuid4())

    log(f"[env] requirement_path={requirement_path}")
    log(f"[env] output_dir={output_dir}")
    log(f"[env] model={os.environ.get('MODEL', '<unset>')}")
    log(
        f"[env] model_endpoint={'set' if os.environ.get('OPENAI_BASE_URL') else 'unset'}"
    )
    log(f"[env] api_key={'set' if os.environ.get('OPENAI_API_KEY') else 'unset'}")
    log(f"[env] grading_port={args.web_port} smoke_port={smoke_port}")

    runtime = AgentRuntime.from_env(project_dir=str(output_dir))
    trace = ProductionTrace(output_dir / ".arc" / "production-trace.jsonl")
    impact = ChangeImpactGraph(output_dir / ".arc" / "change-impact.json")
    events = runtime.events
    events.mark_run_started("factory26 low-token harness started")
    trace.record(
        "run_started",
        run_id=run_id,
        source_identity=source_identity,
        requirement_path=str(requirement_path),
        output_dir=str(output_dir),
        dry_run=args.dry_run,
        manual_interventions=0,
    )

    model: OpenAIChatClient | None = None
    checks: list[CheckResult] = []
    nodes = []
    agent_failures: list[str] = []
    planner_iterations = 0
    coding_agent_iterations = 0
    domain = "unknown"
    execution_route = "not-selected"
    planner_status = "not-started"
    planner_contract: dict[str, Any] | None = None
    coding_agent_enabled = False
    requirement_sha256 = ""
    coverage: CoverageAnalysis | None = None
    nodes_for_agent = []
    transactions: list[dict[str, Any]] = []
    matched_capsules: list[dict[str, Any]] = []
    planner_executor: ThreadPoolExecutor | None = None
    try:
        transactions = _recover_open_transactions(output_dir, runtime, trace, run_id)
        tree = load_requirement_tree(requirement_path)
        requirement_sha256 = requirement_source_sha256(requirement_path)
        nodes = flatten_atomic(tree)
        domain = detect_domain(tree)
        coverage = analyze_coverage(nodes, domain)
        capsule_paths = [
            *args.capability_capsule,
            *[
                item.strip()
                for item in os.environ.get("FACTORY26_CAPABILITY_CAPSULES", "").split(",")
                if item.strip()
            ],
        ]
        for capsule_value in capsule_paths:
            capsule_path = Path(capsule_value).expanduser().resolve()
            capsule = verify_capability_capsule(capsule_path)
            match = match_capability_capsule(capsule, coverage)
            if match["matched"]:
                match["capsule_file_sha256"] = hashlib.sha256(
                    capsule_path.read_bytes()
                ).hexdigest()
                matched_capsules.append(match)
        runtime.traceability.store_requirement_tree(tree)
        plan = plan_payload(nodes, args.batch_size)
        plan["detected_domain"] = domain
        plan["requirement_sha256"] = requirement_sha256
        plan["run_id"] = run_id
        plan["capability_coverage"] = coverage.as_dict()
        plan["capability_memory"] = {
            "matched_capsules": matched_capsules,
            "reuse_skipped_revalidation": False,
        }
        _write_json(output_dir / ".arc" / "compiled-plan.json", plan)
        _write_json(output_dir / ".arc" / "capability-coverage.json", coverage.as_dict())
        trace.record("requirements_compiled", plan=plan)
        trace.record("capability_coverage_analyzed", coverage=coverage.as_dict())
        trace.record(
            "capability_memory_consulted",
            supplied_capsules=len(capsule_paths),
            matched_capsules=matched_capsules,
            reuse_skipped_revalidation=False,
        )

        deterministic_domain = domain in DETERMINISTIC_DOMAINS
        planner_future: Future | None = None
        if args.dry_run:
            planner_status = "skipped-dry-run"
            execution_route = (
                "offline-deterministic-kernel"
                if deterministic_domain
                else "offline-deterministic-scaffold"
            )
            route_reason = "dry-run explicitly disables model planning"
        else:
            model = OpenAIChatClient(trace)
            planner_executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="factory26-planner"
            )
            planner_future = planner_executor.submit(
                SpecificationPlanner(model, trace).plan,
                tree,
                nodes,
            )
            trace.record(
                "speculative_kernel_materialization_started",
                domain=domain,
                planner_running=True,
                policy=(
                    "the deterministic scaffold is a reversible base; only an accepted "
                    "planner contract can promote it to a qualified kernel route"
                ),
            )

        created = scaffold_workspace(output_dir, domain=domain)
        impact.record_requirement_files(("__foundation__",), created)
        for requirement_coverage in coverage.requirements:
            implementation_files = generated_implementation_files(
                domain, requirement_coverage.capabilities
            )
            if implementation_files:
                impact.record_requirement_files(
                    (requirement_coverage.requirement_id,), implementation_files
                )
        trace.record(
            "deterministic_scaffold", tool="scaffold_workspace", created_files=created
        )
        runtime.git.ensure_repo()
        runtime.git.commit("chore: deterministic runnable application foundation")

        for node in nodes:
            events.mark_design_started(
                node.req_id, "compiled from ARC requirement tree"
            )
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
                    scenario.get("id")
                    or scenario.get("scenario_id")
                    or f"scenario-{scenario_index}"
                )
                scenario_id = f"{node.req_id}::{local_scenario_id}"
                runtime.traceability.upsert_scenario(
                    scenario_id=scenario_id,
                    req_id=node.req_id,
                    name=str(scenario.get("name") or local_scenario_id),
                    steps=[
                        dict(step)
                        for step in scenario.get("steps") or []
                        if isinstance(step, dict)
                    ],
                )
                runtime.traceability.upsert_test(
                    test_id=f"contract::{scenario_id}",
                    req_id=node.req_id,
                    type="acceptance_contract",
                    scenario_id=scenario_id,
                    passed=None,
                )
            events.mark_design_done(node.req_id, "requirement contract stored")

        log("[verify] running speculative clean build and startup checks")
        speculative_checks = run_full_checks(output_dir, smoke_port)
        trace.record(
            "speculative_validation_completed",
            planner_running=bool(planner_future and not planner_future.done()),
            promoted=False,
            results=[result.as_dict() for result in speculative_checks],
        )

        if not args.dry_run:
            try:
                if planner_future is None:
                    raise RuntimeError("planner future was not created")
                contract = planner_future.result()
                planner_iterations = contract.iterations
                planner_contract = contract.as_dict()
                planner_status = "completed"
                model_covered_required_capabilities = set(
                    coverage.required_capabilities
                ).issubset(contract.capability_tags)
                kernel_approved = (
                    deterministic_domain
                    and coverage.kernel_eligible
                    and contract.domain == domain
                    and contract.kernel_eligible
                    and model_covered_required_capabilities
                    and not contract.uncovered_requirement_ids
                )
                if kernel_approved:
                    if matched_capsules:
                        execution_route = (
                            "planner-approved-capability-memory-kernel"
                        )
                        route_reason = (
                            "the coverage-blind planner approved the versioned kernel and a prior "
                            "falsifiable capability capsule matched; all validation remains enabled"
                        )
                    else:
                        execution_route = "planner-approved-deterministic-kernel"
                        route_reason = "the planning agent approved the matching versioned domain kernel"
                elif deterministic_domain and (
                    coverage.uncovered_requirement_ids
                    or contract.uncovered_requirement_ids
                ):
                    uncovered_ids = {
                        *coverage.uncovered_requirement_ids,
                        *contract.uncovered_requirement_ids,
                    }
                    nodes_for_agent = [
                        node
                        for node in nodes
                        if node.req_id in uncovered_ids
                    ]
                    coding_agent_enabled = True
                    if contract.domain == domain:
                        execution_route = "planner-routed-kernel-plus-delta-agent"
                        route_reason = (
                            "the versioned kernel covers only part of the compiled requirements; "
                            "a bounded coding agent receives uncovered nodes only"
                        )
                    else:
                        execution_route = (
                            "planner-disagreement-kernel-plus-delta-agent"
                        )
                        route_reason = (
                            "the planner disagreed with deterministic domain analysis while local "
                            "coverage found gaps; the stable kernel is retained and uncovered nodes "
                            "are still routed to a bounded coding agent"
                        )
                elif deterministic_domain:
                    execution_route = "planner-disagreement-bounded-code-agent"
                    route_reason = (
                        "the independent planning contract did not approve the deterministic "
                        "kernel; all requirements are routed to the bounded coding agent"
                    )
                    coding_agent_enabled = True
                    nodes_for_agent = list(nodes)
                else:
                    execution_route = "planner-routed-bounded-code-agent"
                    route_reason = "the planning agent found a kernel mismatch or uncovered capability"
                    coding_agent_enabled = True
                    nodes_for_agent = list(nodes)
            except Exception as exc:
                planner_status = "failed-after-one-attempt"
                trace.record(
                    "planner_failed",
                    error=str(exc),
                    fallback_available=deterministic_domain,
                )
                if not deterministic_domain:
                    raise
                if coverage.uncovered_requirement_ids:
                    execution_route = "planner-failure-kernel-plus-delta-agent"
                    route_reason = (
                        "model planning failed after one attempt; the stable kernel is retained and "
                        "locally proven coverage gaps are still routed to the bounded coding agent"
                    )
                    coding_agent_enabled = True
                    nodes_for_agent = [
                        node
                        for node in nodes
                        if node.req_id in coverage.uncovered_requirement_ids
                    ]
                else:
                    execution_route = "planner-failure-safe-deterministic-kernel"
                    route_reason = "model planning failed after one attempt; the fully covered known kernel is retained for availability"
            finally:
                if planner_executor is not None:
                    planner_executor.shutdown(wait=True, cancel_futures=True)
        plan["execution_route"] = execution_route
        plan["planner_status"] = planner_status
        plan["planner_contract"] = planner_contract
        _write_json(output_dir / ".arc" / "compiled-plan.json", plan)
        _write_json(
            output_dir / ".arc" / "planner-contract.json",
            {
                "version": 1,
                "run_id": run_id,
                "status": planner_status,
                "contract": planner_contract,
                "execution_route": execution_route,
            },
        )
        trace.record(
            "execution_route_selected",
            domain=domain,
            execution_route=execution_route,
            model_invoked=not args.dry_run,
            reason=route_reason,
        )
        trace.record(
            "prompt_decision",
            prompt_invocations_completed=model.request_count if model else 0,
            prompt_invoked=bool(model and model.request_count),
            prompt_source=(
                "factory26_harness/planner.py:PLANNER_SYSTEM_PROMPT"
                if not coding_agent_enabled
                else "planner prompt followed by bounded implementation prompts"
            ),
            reason=route_reason,
        )
        trace.record(
            "human_intervention_checkpoint",
            intervention_required=False,
            intervention_count=0,
            policy="final qualifier execution is autonomous; failures close the gate instead of requesting manual edits",
        )

        if not coding_agent_enabled:
            for node in nodes:
                events.mark_implementation_started(node.req_id, execution_route)
                events.mark_implementation_done(
                    node.req_id,
                    "planner-authorized deterministic kernel materialized",
                )
        else:
            if model is None:
                model = OpenAIChatClient(trace)
            agent_requirement_ids = {node.req_id for node in nodes_for_agent}
            for node in nodes:
                if node.req_id not in agent_requirement_ids:
                    events.mark_implementation_started(node.req_id, execution_route)
                    events.mark_implementation_done(
                        node.req_id,
                        "covered by the materialized versioned capability kernel",
                    )
            for index, group in enumerate(
                batches(nodes_for_agent, args.batch_size), 1
            ):
                ids = [node.req_id for node in group]
                for node in group:
                    events.mark_implementation_started(node.req_id, f"batch {index}")
                related = impact.files_for_requirements(ids)
                checkpoint_head = runtime.git.current_head()
                if not checkpoint_head:
                    raise RuntimeError("cannot open an implementation transaction without a git checkpoint")
                transaction = {
                    "run_id": run_id,
                    "kind": "implementation_batch",
                    "index": index,
                    "requirement_ids": ids,
                    "checkpoint_commit": checkpoint_head,
                    "status": "open",
                    "changed_files": [],
                    "result_commit": None,
                }
                transactions.append(transaction)
                _write_transaction_ledger(
                    output_dir / ".arc" / "transaction-ledger.json", transactions
                )
                trace.record(
                    "agent_batch_checkpointed",
                    requirement_ids=ids,
                    checkpoint_commit=checkpoint_head,
                )
                log(f"[flow] implementing batch {index}: {', '.join(ids)}")
                workspace_tools = WorkspaceTools(output_dir, trace, smoke_port)
                agent = CodingAgent(
                    model, workspace_tools, trace, max_turns=args.max_agent_turns
                )
                try:
                    run = agent.implement(group, related)
                except Exception as exc:
                    run = None
                    agent_failures.extend(ids)
                    trace.record(
                        "agent_batch_failed", requirement_ids=ids, error=str(exc)
                    )
                    log(f"[flow] batch {index} failed: {exc}")
                if run is not None:
                    coding_agent_iterations += run.turns
                    transaction["changed_files"] = list(run.changed_files)
                    trace.record(
                        "agent_batch_result",
                        requirement_ids=ids,
                        completed=run.completed,
                        changed_files=run.changed_files,
                        turns=run.turns,
                        summary=run.summary,
                    )
                    unexpected_paths = _unexpected_transaction_paths(runtime)
                    batch_completed = run.completed and not unexpected_paths
                    if unexpected_paths:
                        transaction["policy_violation_paths"] = list(
                            unexpected_paths
                        )
                        trace.record(
                            "agent_workspace_policy_violation",
                            requirement_ids=ids,
                            unexpected_paths=unexpected_paths,
                        )
                        agent_failures.extend(ids)
                    if batch_completed:
                        impact.record_requirement_files(ids, run.changed_files)
                        _record_file_interfaces(runtime, ids, run.changed_files)
                        runtime.git.commit(
                            f"feat: implement requirements {', '.join(ids)}"
                        )
                        transaction["status"] = "committed"
                        transaction["result_commit"] = runtime.git.current_head()
                    else:
                        agent_failures.extend(ids)
                else:
                    batch_completed = False
                    unexpected_paths = _unexpected_transaction_paths(runtime)
                if not batch_completed:
                    runtime.git.restore_paths(
                        checkpoint_head, ("frontend", "backend")
                    )
                    if unexpected_paths:
                        runtime.git.restore_paths(checkpoint_head, unexpected_paths)
                    transaction["status"] = "rolled_back"
                    trace.record(
                        "agent_batch_rolled_back",
                        requirement_ids=ids,
                        checkpoint_commit=checkpoint_head,
                        attempted_files=transaction["changed_files"],
                    )
                _write_transaction_ledger(
                    output_dir / ".arc" / "transaction-ledger.json", transactions
                )
                for node in group:
                    if node.req_id in agent_failures:
                        events.mark_implementation_failed(
                            node.req_id, "model batch did not complete"
                        )
                    else:
                        events.mark_implementation_done(
                            node.req_id, f"implemented in batch {index}"
                        )

        if coding_agent_enabled:
            trace.record(
                "speculative_validation_discarded",
                reason="bounded coding agent changed or could change the scaffold",
            )
            log("[verify] running final clean build and startup checks")
            checks = run_full_checks(output_dir, smoke_port)
        else:
            checks = speculative_checks
            trace.record(
                "speculative_validation_promoted",
                reason=(
                    "no coding-agent mutation occurred; these become final local checks, "
                    "while release qualification still depends on the planner and black-box gates"
                ),
            )
        for result in checks:
            impact.record_check_files(result.name, result.related_files)
            trace.record("validation_result", tool=result.name, result=result.as_dict())

        if model is not None:
            for repair_round in range(1, max(0, args.repair_rounds) + 1):
                broken = failures(checks)
                if not broken:
                    break
                related = sorted(
                    {path for result in broken for path in result.related_files}
                )
                log(f"[repair] deterministic failure repair round {repair_round}")
                checkpoint_head = runtime.git.current_head()
                if not checkpoint_head:
                    raise RuntimeError("cannot open a repair transaction without a git checkpoint")
                transaction = {
                    "run_id": run_id,
                    "kind": "validation_repair",
                    "index": repair_round,
                    "requirement_ids": [],
                    "checkpoint_commit": checkpoint_head,
                    "status": "open",
                    "changed_files": [],
                    "result_commit": None,
                }
                transactions.append(transaction)
                workspace_tools = WorkspaceTools(output_dir, trace, smoke_port)
                repair_agent = CodingAgent(
                    model, workspace_tools, trace, max_turns=args.max_agent_turns
                )
                run = repair_agent.repair(_failure_text(checks), related)
                coding_agent_iterations += run.turns
                transaction["changed_files"] = list(run.changed_files)
                trace.record(
                    "repair_result",
                    round=repair_round,
                    completed=run.completed,
                    changed_files=run.changed_files,
                    turns=run.turns,
                    summary=run.summary,
                )
                unexpected_paths = _unexpected_transaction_paths(runtime)
                repair_completed = run.completed and not unexpected_paths
                if unexpected_paths:
                    transaction["policy_violation_paths"] = list(unexpected_paths)
                    trace.record(
                        "repair_workspace_policy_violation",
                        round=repair_round,
                        unexpected_paths=unexpected_paths,
                    )
                if repair_completed:
                    runtime.git.commit(
                        f"fix: deterministic validation repair {repair_round}"
                    )
                    transaction["status"] = "committed"
                    transaction["result_commit"] = runtime.git.current_head()
                else:
                    runtime.git.restore_paths(
                        checkpoint_head, ("frontend", "backend")
                    )
                    if unexpected_paths:
                        runtime.git.restore_paths(checkpoint_head, unexpected_paths)
                    transaction["status"] = "rolled_back"
                    trace.record(
                        "repair_rolled_back",
                        round=repair_round,
                        checkpoint_commit=checkpoint_head,
                        attempted_files=run.changed_files,
                    )
                _write_transaction_ledger(
                    output_dir / ".arc" / "transaction-ledger.json", transactions
                )
                checks = run_full_checks(output_dir, smoke_port)
                for result in checks:
                    trace.record(
                        "validation_result",
                        tool=result.name,
                        repair_round=repair_round,
                        result=result.as_dict(),
                    )

        local_passed = all(result.passed for result in checks)
        run_successful = local_passed and not agent_failures
        for node in nodes:
            if not local_passed or node.req_id in agent_failures:
                events.mark_test_failed(
                    node.req_id, "local contract checks or implementation batch failed"
                )
        if run_successful:
            trace.record(
                "behavioral_validation_pending",
                requirement_ids=[node.req_id for node in nodes],
                local_checks_are_behavioral_proof=False,
                required_next_evidence=(
                    "locked public Playwright evaluation"
                    if domain in DETERMINISTIC_DOMAINS
                    else "independent black-box acceptance contract"
                ),
            )
        _write_transaction_ledger(
            output_dir / ".arc" / "transaction-ledger.json", transactions
        )
        runtime.git.commit("chore: final deterministic validation")

        application_source = application_source_manifest(output_dir)
        report = _report(
            started=started,
            nodes=nodes,
            checks=checks,
            model=model,
            agent_failures=sorted(set(agent_failures)),
            dry_run=args.dry_run,
            domain=domain,
            execution_route=execution_route,
            agent_iterations=planner_iterations + coding_agent_iterations,
            planner_status=planner_status,
            planner_contract=planner_contract,
            planner_iterations=planner_iterations,
            coding_agent_iterations=coding_agent_iterations,
            requirement_sha256=requirement_sha256,
            run_id=run_id,
            source_identity=source_identity,
            coverage=coverage,
            transactions=transactions,
            application_source=application_source,
            capability_memory=matched_capsules,
        )
        _write_json(output_dir / ".arc" / "harness-report.json", report)
        trace.record("run_completed", report=report)
        write_run_envelope(output_dir)
        events.mark_run_completed(
            "local contract checks passed"
            if run_successful
            else "completed with implementation or local validation failures"
        )

        artifacts_dir = os.environ.get("ARCBENCH_ARTIFACTS_DIR", "").strip()
        if artifacts_dir:
            _write_json(
                Path(artifacts_dir) / "preview-ready.json",
                {"ready": local_passed, "reason": "harness completed"},
            )
        log(
            f"[done] run {'passed' if run_successful else 'failed'} in {report['duration_seconds']}s"
        )
        return 0 if run_successful or not args.strict_exit else 1
    except Exception as exc:
        if planner_executor is not None:
            planner_executor.shutdown(wait=True, cancel_futures=True)
        trace.record("run_failed", error=str(exc))
        events.mark_run_failed(str(exc)[:1000])
        log(f"[fatal] {exc}")
        return 1 if args.strict_exit else 0


if __name__ == "__main__":
    raise SystemExit(main())
