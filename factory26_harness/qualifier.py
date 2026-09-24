"""Competition-safe, model-driven Factory26 entry point.

The distributed package contains a task-neutral scaffold and general tools.
Every product-specific implementation must be written by the model after it
reads the current requirement tree. A missing model gateway fails closed.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import tempfile
import time
import uuid
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from typing import Any

from .agent import AgentRun, CodingAgent
from .arc_runtime import ArcRuntime
from .checks import CheckResult, run_full_checks
from .generic_scaffold import scaffold_workspace
from .isolation import stage_app_project, validate_app_project
from .model import OpenAIChatClient
from .requirements import (
    RequirementNode,
    batches,
    flatten_atomic,
    load_requirement_tree,
    requirement_source_sha256,
)
from .submission_bundle import (
    SOURCE_MANIFEST_NAME,
    require_external_output_directory,
    verify_source_manifest,
)
from .trace import ProductionTrace
from .visual_reference import VisualReferenceClient, referenced_images
from .workspace_tools import WorkspaceTools


SOURCE_ROOT = Path(__file__).resolve().parents[1]
MAX_HANDOFF_PATHS = 60
MAX_HANDOFF_PATH_CHARS = 4000


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Factory26 model-driven coding agent")
    parser.add_argument(
        "requirements_dir",
        nargs="?",
        default=os.environ.get("ARCBENCH_TASK_DIR", "/workspace/task"),
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--type", "--app-type", dest="app_type", default="web")
    parser.add_argument("--web-port", type=int, default=3000)
    parser.add_argument(
        "--batch-size", type=int, default=int(os.environ.get("FACTORY26_BATCH_SIZE", "4"))
    )
    parser.add_argument(
        "--max-agent-turns",
        type=int,
        default=int(os.environ.get("FACTORY26_MAX_AGENT_TURNS", "20")),
    )
    parser.add_argument(
        "--repair-rounds",
        type=int,
        default=int(os.environ.get("FACTORY26_REPAIR_ROUNDS", "2")),
    )
    parser.add_argument(
        "--salvage-splits",
        type=int,
        choices=(0, 1),
        default=int(os.environ.get("FACTORY26_SALVAGE_SPLITS", "1")),
        help="After a multi-requirement batch fails, retry its two halves once (0 disables)",
    )
    return parser.parse_args(argv)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _smoke_port(web_port: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    if port == web_port:
        return _smoke_port(web_port)
    return port


def _contextual_nodes(
    tree: dict[str, Any], nodes: list[RequirementNode]
) -> list[RequirementNode]:
    """Carry folder context into prompts without encoding any task-specific logic."""
    contexts: dict[str, list[str]] = {}
    inherited_references: dict[str, tuple[str, ...]] = {}
    stack: list[tuple[dict[str, Any], list[str], tuple[str, ...]]] = [
        (tree, [], ())
    ]
    while stack:
        raw, inherited, parent_references = stack.pop()
        children = raw.get("children") or []
        context = inherited
        references = parent_references
        if children:
            name = str(raw.get("name") or "").strip()[:200]
            description = str(raw.get("description") or "").strip()[:1200]
            context = inherited + [" — ".join(value for value in (name, description) if value)]
            raw_references = raw.get("visual_reference") or []
            if not isinstance(raw_references, list):
                raise ValueError("folder visual_reference must be an array")
            references = tuple(
                dict.fromkeys(
                    [
                        *parent_references,
                        *(
                            str(value).strip()[:2000]
                            for value in raw_references
                            if str(value).strip()
                        ),
                    ]
                )
            )
        else:
            identifier = str(raw.get("id") or raw.get("req_id") or "").strip()
            if identifier:
                contexts[identifier] = context
                inherited_references[identifier] = references
        if isinstance(children, list):
            stack.extend(
                (child, context, references)
                for child in reversed(children)
                if isinstance(child, dict)
            )
    return [
        replace(
            node,
            description="\n".join(
                [*(f"Product context: {item}" for item in contexts.get(node.req_id, []) if item), node.description]
            ),
            visual_reference=tuple(
                dict.fromkeys(
                    (
                        *inherited_references.get(node.req_id, ()),
                        *node.visual_reference,
                    )
                )
            ),
        )
        for node in nodes
    ]


def _named_reference_images(nodes: Iterable[RequirementNode]) -> tuple[str, ...]:
    """Honor both images in prose and the explicit visual_reference field."""

    descriptions = [
        text
        for node in nodes
        for text in (node.description, *node.visual_reference)
    ]
    return referenced_images(descriptions)


def _source_identity() -> dict[str, Any]:
    if (SOURCE_ROOT / SOURCE_MANIFEST_NAME).is_file():
        manifest = verify_source_manifest(SOURCE_ROOT)
        return {
            "source": "verified-submission-manifest",
            "revision": manifest["source_revision"],
            "contract_sha256": manifest["contract_sha256"],
        }
    return {"source": "unbundled-development-tree", "revision": None}


def _check_results(results: list[CheckResult]) -> list[dict[str, Any]]:
    return [result.as_dict() for result in results]


def _behavioral_probe_tested(report: dict[str, Any]) -> bool:
    """A later source repair invalidates an earlier browser-probe claim."""

    batches = [
        item for item in report["browser_probe_batches"]
        if item.get("committed", True)
    ]
    repairs = report["browser_probe_repairs"]
    return (
        bool(batches)
        and all(item["behavioral_probe_verified"] for item in batches)
        and all(
            not item["changed_files"] or item["behavioral_probe_verified"]
            for item in repairs
        )
    )


def _recent_handoff_paths(
    previous: list[str], changed: Iterable[str]
) -> list[str]:
    """Retain a bounded, recency-ordered index of files edited by earlier batches."""

    recent = list(previous)
    for value in changed:
        path = str(value)
        if not path or len(path) > 240 or any(ord(char) < 32 for char in path):
            continue
        if path in recent:
            recent.remove(path)
        recent.append(path)
    chosen: list[str] = []
    characters = 0
    for path in reversed(recent):
        if len(chosen) >= MAX_HANDOFF_PATHS:
            break
        if characters + len(path) > MAX_HANDOFF_PATH_CHARS:
            break
        chosen.append(path)
        characters += len(path)
    return list(reversed(chosen))


def _promote_staged_app(staged: Path, output: Path) -> None:
    """Replace only agent-owned app trees, restoring the last good trees on error."""

    validate_app_project(staged)
    # The model executes only in a private system temp directory. Copy its
    # validated result to the output filesystem after it has stopped, then
    # use same-filesystem renames for a rollback-capable promotion.
    with tempfile.TemporaryDirectory(
        prefix="factory26-promote-", dir=output.parent
    ) as promotion_directory:
        promotion = Path(promotion_directory)
        for component in ("frontend", "backend"):
            shutil.copytree(staged / component, promotion / component, symlinks=True)
        validate_app_project(promotion)
        backup = promotion / ".previous-app"
        backup.mkdir()
        promoted: list[str] = []
        try:
            for component in ("frontend", "backend"):
                current = output / component
                candidate = promotion / component
                previous = backup / component
                current.rename(previous)
                try:
                    candidate.rename(current)
                except BaseException:
                    previous.rename(current)
                    raise
                promoted.append(component)
            validate_app_project(output)
        except BaseException:
            for component in reversed(promoted):
                (output / component).rename(promotion / component)
                (backup / component).rename(output / component)
            raise


def _report_arc_failure(
    runtime: ArcRuntime | None, requirement_ids: list[str], reason: str
) -> list[str]:
    """Attempt the run-level failure event even if a per-node event fails."""

    if runtime is None:
        return []
    errors: list[str] = []
    if requirement_ids:
        try:
            runtime.fail_batch(requirement_ids, reason)
        except Exception as exc:
            errors.append(f"requirement failure event: {exc}"[:500])
    try:
        runtime.fail(reason)
    except Exception as exc:
        errors.append(f"run failure event: {exc}"[:500])
    return errors


def main(argv: list[str] | None = None) -> int:
    args = _arguments(argv)
    if args.app_type != "web":
        raise SystemExit("only web applications are supported")
    if args.batch_size < 1 or args.batch_size > 12:
        raise SystemExit("batch size must be between 1 and 12")
    if args.max_agent_turns < 3 or args.max_agent_turns > 80:
        raise SystemExit("max agent turns must be between 3 and 80")
    if args.repair_rounds < 0 or args.repair_rounds > 5:
        raise SystemExit("repair rounds must be between 0 and 5")

    requirement_dir = Path(args.requirements_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    require_external_output_directory(SOURCE_ROOT, output_dir)
    if output_dir == SOURCE_ROOT or SOURCE_ROOT in output_dir.parents:
        raise SystemExit("output directory must be outside the agent source tree")
    if output_dir == requirement_dir or requirement_dir in output_dir.parents:
        raise SystemExit("output directory must not be inside the requirements directory")
    if output_dir.exists():
        unexpected = {
            item.name for item in output_dir.iterdir()
        } - {"requirements", ".arc"}
        prior_agent_artifacts = any(
            (output_dir / ".arc" / name).exists()
            for name in (
                "production-trace.jsonl",
                "compiled-plan.json",
                "harness-report.json",
            )
        )
        if unexpected or prior_agent_artifacts:
            raise SystemExit("output directory contains prior agent work or unexpected files")
    output_dir.mkdir(parents=True, exist_ok=True)
    trace = ProductionTrace(output_dir / ".arc" / "production-trace.jsonl")
    started = time.monotonic()
    run_id = str(uuid.uuid4())
    report: dict[str, Any] = {
        "schema": "langqi-forge-qualifier-v1",
        "run_id": run_id,
        "status": "running",
        "manual_interventions": 0,
        "implemented_requirements": [],
        "failed_requirements": [],
        "checks": [],
        "browser_probe_batches": [],
        "browser_probe_repairs": [],
        "salvage_splits": args.salvage_splits,
        "salvage_attempts": 0,
    }
    model: OpenAIChatClient | None = None
    visual_client: VisualReferenceClient | None = None
    arc_runtime: ArcRuntime | None = None
    active_batch_ids: list[str] = []
    handoff_paths: list[str] = []
    try:
        source = _source_identity()
        tree = load_requirement_tree(requirement_dir)
        nodes = _contextual_nodes(tree, flatten_atomic(tree))
        groups = batches(nodes, args.batch_size)
        requirement_sha = requirement_source_sha256(requirement_dir)
        report.update(
            source=source,
            requirement_sha256=requirement_sha,
            requirement_count=len(nodes),
        )
        arc_runtime = ArcRuntime.connect(output_dir)
        report["arcbench_runtime"] = (
            "official-sdk" if arc_runtime is not None else "unavailable-outside-runner"
        )
        trace.record("arcbench_runtime_selected", status=report["arcbench_runtime"])
        if arc_runtime is not None:
            arc_runtime.start(tree)
        trace.record(
            "run_started",
            run_id=run_id,
            source=source,
            requirement_sha256=requirement_sha,
            requirement_ids=[node.req_id for node in nodes],
            manual_interventions=0,
        )
        _write_json(
            output_dir / ".arc" / "compiled-plan.json",
            {
                "run_id": run_id,
                "requirement_sha256": requirement_sha,
                "batches": [
                    [node.req_id for node in group]
                    for group in groups
                ],
                "salvage_splits": args.salvage_splits,
                "route": "model-generated-implementation",
                "task_specific_prebuilt_code": False,
            },
        )
        created = scaffold_workspace(output_dir)
        trace.record("generic_scaffold_created", files=created)
        if arc_runtime is not None:
            arc_runtime.commit_scaffold()
        smoke_port = _smoke_port(args.web_port)
        initial_checks = run_full_checks(output_dir, smoke_port)
        trace.record("generic_scaffold_checked", checks=_check_results(initial_checks))
        if not all(check.passed for check in initial_checks):
            raise RuntimeError("generic scaffold failed its own build/start checks")

        model = OpenAIChatClient(
            trace,
            planned_turns=(
                len(groups) * (1 + 2 * args.salvage_splits) + args.repair_rounds
            ) * args.max_agent_turns,
        )
        trace.record(
            "model_gateway_selected",
            gateway=model.gateway_evidence(),
            budget=model.budget_evidence(),
            key_present=True,
        )
        trace.record(
            "human_intervention_checkpoint",
            intervention_required=False,
            intervention_count=0,
            policy=(
                "autonomous generation; failed batches discard unverified edits and "
                "may receive one bounded split retry; dependent requirements remain "
                "failed while independent batches may continue"
            ),
        )
        visual_settings = tuple(
            bool(os.environ.get(name, "").strip())
            for name in ("VISUAL_API_KEY", "VISUAL_BASE_URL", "VISUAL_MODEL")
        )
        if all(visual_settings):
            visual_client = VisualReferenceClient(requirement_dir, trace)
            trace.record(
                "visual_gateway_selected",
                model=visual_client.model,
                maximum_calls=visual_client.max_calls,
            )
        elif any(visual_settings):
            trace.record(
                "visual_gateway_unavailable",
                reason="incomplete VISUAL_API_KEY/VISUAL_BASE_URL/VISUAL_MODEL configuration",
            )
        failed_ids: set[str] = set()
        for index, group in enumerate(groups, 1):
            pending: list[tuple[list[RequirementNode], int]] = [(group, 0)]
            attempt = 0
            while pending:
                candidates, split_depth = pending.pop(0)
                blocked: list[RequirementNode] = []
                for node in candidates:
                    if any(dependency in failed_ids for dependency in node.dependencies):
                        blocked.append(node)
                        failed_ids.add(node.req_id)
                if blocked:
                    blocked_ids = [node.req_id for node in blocked]
                    report["failed_requirements"].extend(blocked_ids)
                    trace.record(
                        "implementation_dependency_blocked",
                        batch=index,
                        requirement_ids=blocked_ids,
                        failed_dependencies=sorted(
                            {dependency for node in blocked for dependency in node.dependencies if dependency in failed_ids}
                        ),
                    )
                    if arc_runtime is not None:
                        arc_runtime.fail_batch(blocked_ids, "Prerequisite implementation failed")
                active_group = [node for node in candidates if node not in blocked]
                if not active_group:
                    continue
                attempt += 1
                if split_depth:
                    report["salvage_attempts"] += 1
                requirement_ids = [node.req_id for node in active_group]
                active_batch_ids = requirement_ids
                if arc_runtime is not None:
                    arc_runtime.begin_batch(requirement_ids)
                named_references = _named_reference_images(active_group)
                reference_paths = tuple(
                    path
                    for path in named_references
                    if visual_client is not None and visual_client.can_inspect(path)
                )
                trace.record(
                    "implementation_batch_started",
                    batch=index,
                    attempt=attempt,
                    split_depth=split_depth,
                    requirement_ids=requirement_ids,
                    prior_source_paths=handoff_paths,
                    visual_references_available=reference_paths,
                    visual_references_unavailable=sorted(set(named_references) - set(reference_paths))
                    if visual_client is not None else [],
                )
                # Failed attempts never leak tentative edits into later attempts.
                with tempfile.TemporaryDirectory(
                    prefix="factory26-batch-"
                ) as staged_directory:
                    staged = Path(staged_directory)
                    stage_app_project(output_dir, staged)
                    tools = WorkspaceTools(
                        staged,
                        trace,
                        smoke_port,
                        visual_client=visual_client,
                        reference_paths=reference_paths,
                    )
                    model_exception = False
                    try:
                        result = CodingAgent(
                            model, tools, trace, max_turns=args.max_agent_turns
                        ).implement(active_group, related_files=handoff_paths)
                    except RuntimeError as exc:
                        model_exception = True
                        trace.record(
                            "implementation_batch_exception",
                            batch=index,
                            attempt=attempt,
                            requirement_ids=requirement_ids,
                            error=str(exc),
                        )
                        result = AgentRun(
                            False, str(exc), tuple(sorted(tools.changed_files)), 0
                        )
                    if result.completed:
                        _promote_staged_app(staged, output_dir)
                probe_evidence = {
                    "batch": index,
                    "attempt": attempt,
                    "calls": tools.browser_probe_calls,
                    "committed": result.completed,
                    "behavioral_probe_verified": (
                        tools.browser_probe_verified_revision == tools.change_revision
                    ),
                }
                report["browser_probe_batches"].append(probe_evidence)
                trace.record(
                    "implementation_batch_finished",
                    batch=index,
                    attempt=attempt,
                    requirement_ids=requirement_ids,
                    completed=result.completed,
                    changed_files=result.changed_files,
                    turns=result.turns,
                    summary=result.summary,
                    staged_changes_committed=result.completed,
                    browser_probe=probe_evidence,
                )
                if not result.completed:
                    active_batch_ids = []
                    model_limit = getattr(model, "max_requests", None)
                    can_retry = model_limit is None or model.request_count < model_limit
                    if (
                        not model_exception
                        and split_depth < args.salvage_splits
                        and len(active_group) > 1
                        and can_retry
                    ):
                        midpoint = len(active_group) // 2
                        halves = (active_group[:midpoint], active_group[midpoint:])
                        trace.record(
                            "implementation_batch_split",
                            batch=index,
                            failed_attempt=attempt,
                            requirement_ids=requirement_ids,
                            retry_groups=[[node.req_id for node in half] for half in halves],
                            maximum_extra_attempts=2,
                        )
                        pending = [(half, split_depth + 1) for half in halves] + pending
                        continue
                    failed_ids.update(requirement_ids)
                    report["failed_requirements"].extend(requirement_ids)
                    if arc_runtime is not None:
                        arc_runtime.fail_batch(requirement_ids, result.summary)
                    continue
                handoff_paths = _recent_handoff_paths(handoff_paths, result.changed_files)
                if arc_runtime is not None:
                    arc_runtime.finish_batch(index, requirement_ids)
                report["implemented_requirements"].extend(requirement_ids)
                active_batch_ids = []

        if not report["implemented_requirements"]:
            raise RuntimeError("no requirement batch completed; refusing empty scaffold")

        checks = run_full_checks(output_dir, smoke_port)
        trace.record("final_validation", checks=_check_results(checks))
        for repair_round in range(1, args.repair_rounds + 1):
            if all(check.passed for check in checks):
                break
            failure_text = "\n".join(
                check.summary for check in checks if not check.passed
            )
            related = sorted(
                {
                    path
                    for check in checks
                    if not check.passed
                    for path in check.related_files
                }
            )
            trace.record("repair_started", round=repair_round, failures=failure_text)
            repair_tools = WorkspaceTools(output_dir, trace, smoke_port)
            repair = CodingAgent(
                model, repair_tools, trace, max_turns=args.max_agent_turns
            ).repair(failure_text, related)
            repair_probe_evidence = {
                "round": repair_round,
                "changed_files": repair.changed_files,
                "calls": repair_tools.browser_probe_calls,
                "behavioral_probe_verified": (
                    repair_tools.browser_probe_verified_revision
                    == repair_tools.change_revision
                ),
            }
            report["browser_probe_repairs"].append(repair_probe_evidence)
            trace.record(
                "repair_finished",
                round=repair_round,
                completed=repair.completed,
                changed_files=repair.changed_files,
                turns=repair.turns,
                browser_probe=repair_probe_evidence,
            )
            if not repair.completed:
                break
            checks = run_full_checks(output_dir, smoke_port)
            trace.record("final_validation", repair_round=repair_round, checks=_check_results(checks))
            if arc_runtime is not None:
                arc_runtime.commit_repairs()

        report["checks"] = _check_results(checks)
        if not all(check.passed for check in checks):
            raise RuntimeError("final build/start validation failed")
        if model.request_count < 1:
            raise RuntimeError("no model request completed")
        report["status"] = (
            "local-contract-partial"
            if report["failed_requirements"]
            else "local-contract-passed"
        )
        report["behavioral_probe_tested"] = _behavioral_probe_tested(report)
        # Only the platform's separate GUI suite can set this distinction.
        report["behavioral_gui_tested"] = False
        if arc_runtime is not None:
            if report["failed_requirements"]:
                arc_runtime.commit_failed_requirements()
            arc_runtime.complete(partial=bool(report["failed_requirements"]))
        trace.record(
            "run_completed",
            status=report["status"],
            model_requests=model.request_count,
            model_http_attempts=getattr(model, "http_attempt_count", None),
            note="independent GUI acceptance remains the platform's responsibility",
        )
        return 0
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        sdk_errors = _report_arc_failure(arc_runtime, active_batch_ids, str(exc))
        if sdk_errors:
            report["arcbench_runtime_error"] = "; ".join(sdk_errors)[:1000]
        trace.record("run_failed", error=str(exc), arcbench_runtime_errors=sdk_errors)
        print(f"[factory26] failed: {exc}", flush=True)
        return 1
    finally:
        report["duration_seconds"] = round(time.monotonic() - started, 3)
        if model is not None:
            report["model"] = model.gateway_evidence()
            report["model_budget"] = model.budget_evidence()
            report["model_requests"] = model.request_count
            report["model_http_attempts"] = getattr(model, "http_attempt_count", None)
            report["prompt_tokens"] = model.total_prompt_tokens
            report["completion_tokens"] = model.total_completion_tokens
        if visual_client is not None:
            report["visual_model"] = visual_client.model
            report["visual_requests"] = visual_client.calls
            report["visual_prompt_tokens"] = visual_client.prompt_tokens
            report["visual_completion_tokens"] = visual_client.completion_tokens
        _write_json(output_dir / ".arc" / "harness-report.json", report)
        print(
            f"[factory26] {report['status']}; model_requests={report.get('model_requests', 0)}",
            flush=True,
        )


if __name__ == "__main__":
    raise SystemExit(main())
