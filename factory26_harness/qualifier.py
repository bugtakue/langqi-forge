"""Competition-safe Factory26 entry point.

The model writes frontend/ and backend/ through the four-layer contract in
architecture.py. A batch that never edits the scaffold fails closed.
"""

from __future__ import annotations

import argparse
import hashlib
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
from .agent_first_fallback import AgentFirstFallbackGraph, FallbackExecution
from .architecture import describe_run
from .arc_runtime import ArcRuntime
from .checks import CheckResult, run_full_checks
from .generic_scaffold import scaffold_workspace
from .isolation import app_source_manifest, stage_app_project, validate_app_project
from .model import ModelBudgetExceeded, ModelGatewayUnavailable, OpenAIChatClient
from .regression import RegressionMemory, recheck_candidate_flows
from .requirements import (
    RequirementNode,
    flatten_atomic,
    folder_dependency_index,
    load_requirement_tree,
    requirement_source_sha256,
)
from .submission_bundle import (
    SOURCE_MANIFEST_NAME,
    require_external_output_directory,
    verify_source_manifest,
)
from .trace import ProductionTrace
from .visual_reference import VisualReferenceClient, referenced_images, resolve_visual_gateway
from .workspace_tools import WorkspaceTools


SOURCE_ROOT = Path(__file__).resolve().parents[1]
MAX_HANDOFF_PATHS = 60
MAX_HANDOFF_PATH_CHARS = 4000
MAX_HANDOFF_NOTES = 4
MAX_HANDOFF_NOTE_CHARS = 700
MAX_HANDOFF_NOTES_CHARS = 2400


def _guarded_checks(
    root: Path, port: int, regression: RegressionMemory, *,
    requirement_ids: tuple[str, ...] = (), final: bool = False,
) -> list[CheckResult]:
    checks = list(run_full_checks(root, port))
    if all(check.passed for check in checks) and regression.summary()["capsule_count"]:
        checks.append(regression.check(root, port, requirement_ids=requirement_ids, final=final))
    return checks


def _dependency_ids(nodes: list[RequirementNode]) -> tuple[str, ...]:
    return tuple(sorted({dependency for node in nodes for dependency in node.dependencies}))


def _remember_behavior(
    regression: RegressionMemory, tools: WorkspaceTools,
    requirement_ids: list[str], output_dir: Path,
    *, verified_flows: list[list[dict]] | None = None,
) -> None:
    flows = tools.verified_browser_flows if verified_flows is None else verified_flows
    if flows:
        source_manifest = app_source_manifest(output_dir)
        for steps in flows:
            regression.remember(requirement_ids, steps, source_manifest)


def _public_failure_summary(check: CheckResult) -> str:
    return ("Stored behavior replay failed; see sealed candidate checks."
            if check.name == "behavior_regression" else check.summary)


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
        "--batch-spec-chars", type=int,
        default=int(os.environ.get("FACTORY26_BATCH_SPEC_CHARS", "32000")),
        help="Bound public specification size per batch; a single larger requirement stays intact",
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
    parser.add_argument(
        "--agent-first-fallback",
        action=argparse.BooleanOptionalAction,
        default=os.environ.get("FACTORY26_AGENT_FIRST_FALLBACK", "0").strip() == "1",
        help=(
            "Run the normal Agent first and allow exactly one same-boundary "
            "deterministic recovery after independent acceptance failure"
        ),
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


def _occupied_smoke_port(checks: list[CheckResult]) -> bool:
    """Distinguish a port-allocation race from an application failure."""

    return (
        bool(checks)
        and all(check.passed for check in checks[:-1])
        and checks[-1].name == "startup_health"
        and not checks[-1].passed
        and checks[-1].summary.startswith("smoke port ")
        and checks[-1].summary.endswith(" is already occupied")
    )


def _contextual_nodes(
    tree: dict[str, Any], nodes: list[RequirementNode]
) -> list[RequirementNode]:
    """Carry folder context into prompts without encoding any task-specific logic."""
    contexts: dict[str, list[str]] = {}
    full_contexts: dict[str, tuple[str, ...]] = {}
    context_abbreviations: dict[str, bool] = {}
    inherited_references: dict[str, tuple[str, ...]] = {}
    stack: list[tuple[dict[str, Any], list[str], tuple[str, ...], tuple[str, ...], bool]] = [
        (tree, [], (), (), False)
    ]
    while stack:
        raw, inherited, full_inherited, parent_references, parent_abbreviated = stack.pop()
        children = raw.get("children") or []
        context = inherited
        full_context = full_inherited
        context_abbreviated = parent_abbreviated
        references = parent_references
        if children:
            full_name = str(raw.get("name") or "").strip()
            full_description = str(raw.get("description") or "").strip()
            folder_dependencies = raw.get("dependencies") or []
            if not isinstance(folder_dependencies, list):
                raise ValueError("folder dependencies must be an array")
            dependency_names = [str(value).strip() for value in folder_dependencies]
            if any(not value for value in dependency_names):
                raise ValueError("folder dependency id is missing")
            short_context = " — ".join(
                value for value in (full_name[:200], full_description[:1200]) if value
            )
            if dependency_names:
                short_context += (
                    " | Folder dependencies: "
                    + ", ".join(value[:160] for value in dependency_names[:20])
                )
            context = inherited + [short_context]
            # A full-spec read must recover *all* ancestor metadata, not just
            # the fields known to this version of the prompt compiler.
            full_context = full_inherited + (json.dumps(
                {key: value for key, value in raw.items() if key != "children"},
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),)
            inline_folder_fields = {
                "id", "req_id", "type", "name", "description",
                "dependencies", "visual_reference", "children",
            }
            context_abbreviated = (
                parent_abbreviated
                or len(full_name) > 200
                or len(full_description) > 1200
                or len(dependency_names) > 20
                or any(len(value) > 160 for value in dependency_names)
                or bool(raw.keys() - inline_folder_fields)
            )
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
                full_contexts[identifier] = full_context
                context_abbreviations[identifier] = context_abbreviated
                inherited_references[identifier] = references
        if isinstance(children, list):
            stack.extend(
                (child, context, full_context, references, context_abbreviated)
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
            full_context=full_contexts.get(node.req_id, ()),
            context_abbreviated=context_abbreviations.get(node.req_id, False),
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
    repairs = [
        item for item in report["browser_probe_repairs"]
        if item.get("committed", True)
    ]
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


def _recent_handoff_notes(
    previous: tuple[str, ...], requirement_ids: list[str], summary: str
) -> tuple[str, ...]:
    """Carry only short, successful model summaries; source remains authoritative."""

    description = " ".join(str(summary).split())[:MAX_HANDOFF_NOTE_CHARS]
    identifiers = ",".join(requirement_ids)[:200]
    if not description or not identifiers:
        return previous
    recent = (*previous, f"{identifiers}: {description}")
    chosen: list[str] = []
    total_characters = 0
    for note in reversed(recent):
        if len(chosen) >= MAX_HANDOFF_NOTES or total_characters + len(note) > MAX_HANDOFF_NOTES_CHARS:
            break
        chosen.append(note)
        total_characters += len(note)
    return tuple(reversed(chosen))


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


def _run_agent_first_fallback(
    graph: AgentFirstFallbackGraph,
    tree: dict[str, Any],
    output_dir: Path,
    smoke_port: int,
    regression: RegressionMemory,
    trace: ProductionTrace,
) -> FallbackExecution:
    """Run the single deterministic retry from a fresh last-good application copy."""

    if not graph.can_attempt_fallback():
        return FallbackExecution(
            attempted=False,
            applied=False,
            passed=False,
            name=graph.binding.name if graph.binding else None,
            covered_ids=(),
            changed_files=(),
            checks=(),
            summary="No eligible same-boundary deterministic fallback",
        )

    binding = graph.start_fallback()
    changed_files = (
        "frontend/src/app.js",
        "frontend/src/styles.css",
        "backend/server.mjs",
    )
    checks: list[CheckResult] = []
    applied = False
    passed = False
    source_sha256: str | None = None
    failure = ""
    covered_ids = tuple(
        req_id
        for req_id in graph.context.requirement_ids
        if req_id in set(binding.covered_ids)
    )
    with tempfile.TemporaryDirectory(prefix="factory26-deterministic-fallback-") as directory:
        staged = Path(directory)
        try:
            # The failed Agent copy is discarded.  Recovery always starts from
            # the last promoted application, so a half-written model patch
            # cannot leak into the second attempt.
            stage_app_project(output_dir, staged)
            applied = bool(binding.apply(staged, tree))
            if not applied:
                failure = "fallback binding refused the public requirement tree"
            else:
                checks = _guarded_checks(staged, smoke_port, regression, final=True)
                passed = all(check.passed for check in checks)
                if passed:
                    _promote_staged_app(staged, output_dir)
                    manifest = app_source_manifest(output_dir)
                    source_sha256 = hashlib.sha256(
                        json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
                    ).hexdigest()
                else:
                    failure = "; ".join(
                        check.summary for check in checks if not check.passed
                    )[:1200]
        except Exception as exc:  # recovery must fail closed and remain auditable
            failure = f"{type(exc).__name__}: {exc}"[:1200]

    summary = (
        f"{binding.name} fallback passed independent checks"
        if passed
        else failure or f"{binding.name} fallback did not pass independent checks"
    )
    graph.finish_fallback(
        passed=passed,
        covered_ids=covered_ids,
        source_sha256=source_sha256,
        summary=summary,
    )
    trace.record(
        "harness_fallback_validation",
        fallback=binding.name,
        applied=applied,
        passed=passed,
        requirement_ids=list(graph.context.active_ids),
        covered_ids=list(covered_ids),
        checks=_check_results(checks),
        summary=summary,
    )
    return FallbackExecution(
        attempted=True,
        applied=applied,
        passed=passed,
        name=binding.name,
        covered_ids=covered_ids,
        changed_files=changed_files if applied else (),
        checks=tuple(_check_results(checks)),
        summary=summary,
    )


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
    if not 4000 <= args.batch_spec_chars <= 200000:
        raise SystemExit("batch specification budget must be between 4000 and 200000 characters")
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
    trace = ProductionTrace(
        output_dir / ".arc" / "production-trace.jsonl", stdout_progress=True
    )
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
        "candidate_validations": [],
        "browser_probe_batches": [],
        "browser_probe_repairs": [],
        "salvage_splits": args.salvage_splits,
        "salvage_attempts": 0,
    }
    model: OpenAIChatClient | None = None
    visual_client: VisualReferenceClient | None = None
    arc_runtime: ArcRuntime | None = None
    graph: AgentFirstFallbackGraph | None = None
    fallback_graph_active = False
    fallback_recovered = False
    active_batch_ids: list[str] = []
    handoff_paths: list[str] = []
    handoff_notes: tuple[str, ...] = ()
    regression = RegressionMemory(trace)
    try:
        source = _source_identity()
        tree = load_requirement_tree(requirement_dir)
        nodes = _contextual_nodes(tree, flatten_atomic(tree))
        plan = describe_run(
            tree,
            nodes,
            batch_size=args.batch_size,
            batch_spec_chars=args.batch_spec_chars,
            max_turns=args.max_agent_turns,
            repair_rounds=args.repair_rounds,
        )
        groups = [list(group) for group in plan.groups]
        outline = plan.outline
        outline_index = plan.outline_index
        architecture = plan.public_record()
        outline_listed = int(outline_index["listed_requirements"])
        folder_index = folder_dependency_index(tree)
        requirement_sha = requirement_source_sha256(requirement_dir)
        if args.agent_first_fallback:
            graph = AgentFirstFallbackGraph(
                run_id=run_id,
                requirement_sha256=requirement_sha,
                requirement_ids=[node.req_id for node in nodes],
                tree=tree,
                trace=trace,
            )
            fallback_graph_active = graph.fallback_available
        report.update(
            source=source,
            requirement_sha256=requirement_sha,
            requirement_count=len(nodes),
            harness_mode=(
                "agent-first-with-one-deterministic-fallback"
                if fallback_graph_active
                else "agent-first-no-task-specific-fallback"
                if args.agent_first_fallback
                else "legacy-bounded-agent"
            ),
            agent_first_fallback=(graph.summary() if graph is not None else None),
            batch_spec_chars=args.batch_spec_chars,
            task_outline_listed_requirements=outline_listed,
            task_outline_listed_folder_dependencies=int(outline_index["listed_folder_dependencies"]),
            task_outline_characters=len(outline),
            architecture=architecture,
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
        trace.record(
            "task_outline_compiled",
            listed_requirements=outline_listed,
            total_requirements=len(nodes),
            listed_folder_dependencies=int(outline_index["listed_folder_dependencies"]),
            total_folder_dependencies=len(folder_index),
            characters=len(outline),
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
                "folder_dependencies": folder_index,
                "salvage_splits": args.salvage_splits,
                "batch_spec_chars": args.batch_spec_chars,
                "route": "model-generated-implementation",
                "task_specific_prebuilt_code": bool(fallback_graph_active),
                "agent_first_fallback": bool(args.agent_first_fallback),
                "architecture": architecture,
            },
        )
        created = scaffold_workspace(output_dir)
        trace.record("generic_scaffold_created", files=created)
        if arc_runtime is not None:
            arc_runtime.commit_scaffold()
        smoke_port = _smoke_port(args.web_port)
        initial_checks: list[CheckResult] = []
        report["initial_check_attempts"] = []
        for check_attempt in (1, 2):
            initial_checks = run_full_checks(output_dir, smoke_port)
            evidence = _check_results(initial_checks)
            report["initial_check_attempts"].append(evidence)
            report["initial_checks"] = evidence
            trace.record(
                "generic_scaffold_checked",
                attempt=check_attempt,
                smoke_port=smoke_port,
                checks=evidence,
            )
            if check_attempt == 2 or not _occupied_smoke_port(initial_checks):
                break
            smoke_port = _smoke_port(args.web_port)
        if not all(check.passed for check in initial_checks):
            raise RuntimeError("generic scaffold failed its own build/start checks")

        model = OpenAIChatClient(
            trace,
            planned_turns=(
                # Every implementation attempt may need one isolated startup
                # repair before it is safe to promote to the next batch.
                len(groups) * (1 + 2 * args.salvage_splits) * 2
                + args.repair_rounds
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
        visual_configuration, visual_status = resolve_visual_gateway()
        if visual_configuration is not None:
            try:
                visual_client = VisualReferenceClient(
                    requirement_dir, trace, visual_configuration
                )
            except ValueError:
                trace.record(
                    "visual_gateway_unavailable",
                    reason="visual gateway endpoint or call budget is invalid",
                )
            else:
                trace.record(
                    "visual_gateway_selected",
                    model=visual_client.model,
                    source=visual_client.gateway_source,
                    maximum_calls=visual_client.max_calls,
                )
        elif visual_status != "disabled":
            trace.record(
                "visual_gateway_unavailable",
                reason=visual_status,
            )
        failed_ids: set[str] = set()
        terminal_model_error: str | None = None
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
                if arc_runtime is not None and not (
                    graph is not None and graph.context.continuation
                ):
                    arc_runtime.begin_batch(requirement_ids)
                if fallback_graph_active:
                    graph.begin_batch(requirement_ids)
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
                    prior_handoff_count=len(handoff_notes),
                    visual_inspection_enabled=visual_client is not None,
                    visual_references_available=reference_paths,
                    visual_references_unavailable=sorted(set(named_references) - set(reference_paths)),
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
                        handoff_notes=handoff_notes,
                    )
                    model_exception = False
                    fallback_execution: FallbackExecution | None = None
                    try:
                        agent_task_outline = outline
                        if fallback_graph_active:
                            agent_task_outline += "\n\n" + graph.model_context()
                        result = CodingAgent(
                            model, tools, trace, max_turns=args.max_agent_turns
                        ).implement(
                            active_group,
                            related_files=handoff_paths,
                            task_outline=agent_task_outline,
                            accepted_ids=report["implemented_requirements"],
                        )
                    except RuntimeError as exc:
                        model_exception = True
                        if isinstance(exc, (ModelGatewayUnavailable, ModelBudgetExceeded)):
                            terminal_model_error = str(exc)
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
                    if fallback_graph_active:
                        graph.agent_result(result.completed, result.summary)
                    # Capture before repair can replace the last successful probe
                    # with a reproduction of an unrelated older regression.
                    candidate_flows = tools.verified_browser_flows if result.completed else []
                    if result.completed:
                        # Quick validation proves a fresh frontend build, but it
                        # cannot catch a syntactically valid backend that crashes
                        # on startup. Check the isolated candidate before it can
                        # become the base for later requirement batches.
                        candidate_checks = _guarded_checks(
                            staged, smoke_port, regression, requirement_ids=_dependency_ids(active_group),
                        )
                        candidate_passed = all(check.passed for check in candidate_checks)
                        candidate_validation: dict[str, Any] = {
                            "batch": index,
                            "attempt": attempt,
                            "requirement_ids": requirement_ids,
                            "passed_before_repair": candidate_passed,
                            "repair_attempted": False,
                            "passed_after_repair": None,
                        }
                        report["candidate_validations"].append(candidate_validation)
                        trace.record(
                            "implementation_candidate_validation",
                            batch=index,
                            attempt=attempt,
                            phase="before_repair",
                            checks=_check_results(candidate_checks),
                        )
                        if fallback_graph_active:
                            candidate_validation["fallback_attempted"] = False
                            candidate_validation["passed_after_fallback"] = None
                            failure_text = "\n".join(
                                check.summary for check in candidate_checks if not check.passed
                            )
                            graph.validation_result(candidate_passed, failure_text)
                            if candidate_passed and not graph.context.fallback_attempted:
                                graph.release_for_covered_canvas()
                            if graph.can_attempt_fallback():
                                fallback_execution = _run_agent_first_fallback(
                                    graph,
                                    tree,
                                    output_dir,
                                    smoke_port,
                                    regression,
                                    trace,
                                )
                                candidate_validation["fallback_attempted"] = (
                                    fallback_execution.attempted
                                )
                                candidate_validation["passed_after_fallback"] = (
                                    fallback_execution.passed
                                )
                                if fallback_execution.passed:
                                    fallback_recovered = True
                                    result = AgentRun(
                                        True,
                                        result.summary + "\n\n" + fallback_execution.summary,
                                        fallback_execution.changed_files,
                                        result.turns,
                                    )
                                elif not candidate_passed:
                                    result = AgentRun(
                                        False,
                                        fallback_execution.summary,
                                        tuple(sorted(tools.changed_files)),
                                        result.turns,
                                    )
                                if not fallback_execution.attempted:
                                    graph.fail_terminal(fallback_execution.summary)
                            elif graph.context.continuation and not candidate_passed:
                                result = AgentRun(
                                    False,
                                    "continuation checks failed; recovered canvas kept",
                                    tuple(sorted(tools.changed_files)),
                                    result.turns,
                                )
                                graph.keep_baseline(result.summary)
                        elif not candidate_passed:
                            candidate_validation["repair_attempted"] = True
                            failure_text = "\n".join(
                                check.summary for check in candidate_checks if not check.passed
                            )
                            related = sorted({
                                path
                                for check in candidate_checks
                                if not check.passed
                                for path in check.related_files
                            })
                            trace.record(
                                "implementation_candidate_repair_started",
                                batch=index,
                                attempt=attempt,
                                failures=failure_text,
                                related_files=related,
                            )
                            try:
                                correction = CodingAgent(
                                    model, tools, trace, max_turns=args.max_agent_turns
                                ).repair(
                                    failure_text,
                                    related,
                                    nodes=active_group,
                                    task_outline=outline,
                                    accepted_ids=report["implemented_requirements"],
                                )
                            except RuntimeError as exc:
                                model_exception = True
                                if isinstance(exc, (ModelGatewayUnavailable, ModelBudgetExceeded)):
                                    terminal_model_error = str(exc)
                                trace.record(
                                    "implementation_candidate_repair_exception",
                                    batch=index,
                                    attempt=attempt,
                                    error=str(exc),
                                )
                                correction = AgentRun(False, str(exc), (), 0)
                            if correction.completed:
                                # Recheck ALL saved flows after a repair, not a
                                # rotated sample that could miss the original failure.
                                candidate_checks = _guarded_checks(
                                    staged, smoke_port, regression, final=True,
                                )
                                if all(check.passed for check in candidate_checks) and candidate_flows:
                                    candidate_checks.append(recheck_candidate_flows(
                                        staged, smoke_port, candidate_flows, trace,
                                    ))
                                candidate_passed = all(
                                    check.passed for check in candidate_checks
                                )
                                trace.record(
                                    "implementation_candidate_validation",
                                    batch=index,
                                    attempt=attempt,
                                    phase="after_repair",
                                    checks=_check_results(candidate_checks),
                                )
                            else:
                                candidate_passed = False
                            candidate_validation["passed_after_repair"] = candidate_passed
                            if correction.completed and not candidate_passed:
                                failure_detail = "\n".join(
                                    _public_failure_summary(check)
                                    for check in candidate_checks
                                    if not check.passed
                                )
                            else:
                                failure_detail = correction.summary or "Candidate checks failed; see sealed trace."
                            result = AgentRun(
                                candidate_passed,
                                (
                                    result.summary + "\n\nPost-audit candidate repair: "
                                    + correction.summary
                                    if candidate_passed
                                    else "Post-audit candidate validation failed: "
                                    + failure_detail
                                ),
                                tuple(sorted(tools.changed_files)),
                                result.turns + correction.turns,
                            )
                        just_recovered = (
                            fallback_execution is not None and fallback_execution.passed
                        )
                        if result.completed and not just_recovered:
                            _promote_staged_app(staged, output_dir)
                    if not result.completed and fallback_graph_active and fallback_execution is None:
                        if graph.context.continuation:
                            if graph.context.state != "PLAN":
                                graph.keep_baseline(result.summary)
                        else:
                            fallback_execution = _run_agent_first_fallback(
                                graph,
                                tree,
                                output_dir,
                                smoke_port,
                                regression,
                                trace,
                            )
                            if fallback_execution.passed:
                                fallback_recovered = True
                                result = AgentRun(
                                    True,
                                    result.summary + "\n\n" + fallback_execution.summary,
                                    fallback_execution.changed_files,
                                    result.turns,
                                )
                            elif not fallback_execution.attempted:
                                graph.fail_terminal(fallback_execution.summary)
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
                    if graph is not None and graph.context.continuation:
                        continue
                    model_limit = getattr(model, "max_requests", None)
                    can_retry = model_limit is None or model.request_count < model_limit
                    if (
                        not fallback_graph_active
                        and
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
                    if terminal_model_error is not None:
                        trace.record(
                            "model_gateway_circuit_open",
                            batch=index,
                            requirement_ids=requirement_ids,
                            reason=terminal_model_error,
                        )
                        break
                    continue
                handoff_paths = _recent_handoff_paths(handoff_paths, result.changed_files)
                handoff_notes = _recent_handoff_notes(
                    handoff_notes, requirement_ids, result.summary
                )
                if arc_runtime is not None:
                    just_recovered = (
                        fallback_execution is not None and fallback_execution.passed
                    )
                    if just_recovered and graph is not None:
                        arc_runtime.finish_fallback(
                            list(graph.context.completed_ids),
                            list(graph.context.failed_ids),
                        )
                    elif graph is not None and graph.context.continuation:
                        try:
                            arc_runtime.finish_batch(index, requirement_ids)
                        except RuntimeError as exc:
                            trace.record(
                                "agent_continuation_commit_skipped",
                                batch=index,
                                error=str(exc)[:300],
                            )
                    else:
                        arc_runtime.finish_batch(index, requirement_ids)
                if (
                    fallback_graph_active
                    and graph.context.state == "PROMOTE"
                ):
                    graph.accept_batch()
                _remember_behavior(
                    regression, tools, requirement_ids, output_dir,
                    verified_flows=() if fallback_recovered else candidate_flows,
                )
                report["implemented_requirements"].extend(requirement_ids)
                active_batch_ids = []
                if (
                    fallback_recovered
                    and graph is not None
                    and graph.context.state == "TERMINAL"
                    and not graph.context.continuation
                ):
                    graph.continue_after_fallback()
            if (
                fallback_graph_active
                and graph is not None
                and graph.context.state == "TERMINAL"
                and not fallback_recovered
            ):
                terminal_model_error = graph.context.last_failure or (
                    "Agent and deterministic fallback both failed"
                )
            if terminal_model_error is not None:
                finished_ids = set(report["implemented_requirements"]) | set(
                    report["failed_requirements"]
                )
                remaining_ids = [
                    node.req_id for node in nodes if node.req_id not in finished_ids
                ]
                if remaining_ids:
                    failed_ids.update(remaining_ids)
                    report["failed_requirements"].extend(remaining_ids)
                    trace.record(
                        "implementation_skipped_after_model_failure",
                        requirement_ids=remaining_ids,
                        reason=terminal_model_error,
                    )
                    if arc_runtime is not None:
                        arc_runtime.fail_batch(remaining_ids, terminal_model_error)
                report["model_gateway_stop_reason"] = terminal_model_error
                break

        if fallback_graph_active and graph is not None:
            # A successful deterministic canvas covers its complete public
            # allowlist.  Record that fact once, instead of pretending only
            # the first model batch was delivered.
            if fallback_recovered:
                recovered_ids = list(graph.context.completed_ids)
                report["implemented_requirements"] = recovered_ids
                report["failed_requirements"] = [
                    req_id for req_id in (node.req_id for node in nodes)
                    if req_id not in set(recovered_ids)
                ]
                failed_ids.update(report["failed_requirements"])
            report["agent_first_fallback"] = graph.summary()

        if not report["implemented_requirements"]:
            raise RuntimeError(
                "no requirement batch completed; "
                + (terminal_model_error or "refusing empty scaffold")
            )

        checks = _guarded_checks(output_dir, smoke_port, regression, final=True)
        trace.record("final_validation", checks=_check_results(checks))
        # Once the explicit second lane has run, do not silently turn a final
        # repair into a third model attempt.  A normal all-Agent run retains
        # the legacy bounded repair budget.
        repair_budget = 0 if fallback_recovered else args.repair_rounds
        for repair_round in range(1, repair_budget + 1):
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
            committed = False
            with tempfile.TemporaryDirectory(
                prefix="factory26-repair-"
            ) as staged_directory:
                staged = Path(staged_directory)
                stage_app_project(output_dir, staged)
                repair_tools = WorkspaceTools(staged, trace, smoke_port)
                repair = CodingAgent(
                    model, repair_tools, trace, max_turns=args.max_agent_turns
                ).repair(
                    failure_text,
                    related,
                    nodes=nodes,
                    task_outline=outline,
                    accepted_ids=report["implemented_requirements"],
                )
                if repair.completed:
                    candidate_checks = _guarded_checks(staged, smoke_port, regression, final=True)
                    trace.record(
                        "repair_candidate_validation",
                        round=repair_round,
                        checks=_check_results(candidate_checks),
                    )
                    if all(check.passed for check in candidate_checks):
                        _promote_staged_app(staged, output_dir)
                        committed = True
            repair_probe_evidence = {
                "round": repair_round,
                "changed_files": repair.changed_files,
                "calls": repair_tools.browser_probe_calls,
                "committed": committed,
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
                staged_changes_committed=committed,
                browser_probe=repair_probe_evidence,
            )
            if not committed:
                break
            checks = _guarded_checks(output_dir, smoke_port, regression, final=True)
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
        report["behavioral_regression"] = regression.summary()
        if graph is not None:
            report["agent_first_fallback"] = graph.summary()
            report["fallback_recovered"] = graph.fallback_recovered
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
        try:
            report["evidence_export"] = trace.export_evidence(report)
        except Exception as exc:
            # Evidence delivery failure must be visible, but must not discard a
            # working application or masquerade as a successful export.
            report["evidence_export"] = {
                "status": "failed", "error_type": type(exc).__name__,
            }
        _write_json(output_dir / ".arc" / "harness-report.json", report)
        print("[factory26:evidence] " + json.dumps(report["evidence_export"], sort_keys=True), flush=True)
        print(
            f"[factory26] {report['status']}; model_requests={report.get('model_requests', 0)}",
            flush=True,
        )


if __name__ == "__main__":
    raise SystemExit(main())
