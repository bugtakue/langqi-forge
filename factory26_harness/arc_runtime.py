"""Thin adapter to the official ARC-Bench runtime SDK.

The SDK, not this module, owns runner event payloads, traceability tables and
Git refresh signals. The independent production trace remains a separate audit.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Any


class ArcRuntime:
    def __init__(self, sdk: Any, project_dir: Path) -> None:
        self.sdk = sdk
        self.project_dir = project_dir

    @classmethod
    def connect(cls, project_dir: Path) -> "ArcRuntime | None":
        project_dir = project_dir.expanduser().resolve()
        runner_present = bool(os.environ.get("ARCBENCH_RUNNER_EVENTS_PATH", "").strip())
        try:
            package = importlib.import_module("arcbench_agent_runtime")
        except ModuleNotFoundError as exc:
            if exc.name != "arcbench_agent_runtime":
                raise
            package = None
        factory = getattr(package, "AgentRuntime", None)
        if factory is None:
            if runner_present:
                raise RuntimeError("ARC-Bench runner SDK is unavailable")
            return None
        sdk = factory.from_env(project_dir=str(project_dir))
        expected_arc = project_dir / ".arc"
        if Path(sdk.paths.project_dir).resolve() != project_dir:
            raise RuntimeError("ARC-Bench SDK project directory does not match output")
        if Path(sdk.paths.runner_events_path).resolve() != expected_arc / "runner-events.jsonl":
            raise RuntimeError("ARC-Bench SDK event path does not match output")
        if Path(sdk.paths.traceability_dir).resolve() != expected_arc / "traceability":
            raise RuntimeError("ARC-Bench SDK traceability path does not match output")
        return cls(sdk, project_dir)

    def start(self, requirement_tree: dict[str, Any]) -> None:
        self.sdk.events.mark_run_started("Model-driven agent run started")
        self.sdk.traceability.init_db()
        self.sdk.traceability.store_requirement_tree(requirement_tree)

    def commit_scaffold(self) -> None:
        self.sdk.git.ensure_repo(create_initial_commit=True)

    def begin_batch(self, requirement_ids: list[str]) -> None:
        for req_id in requirement_ids:
            self.sdk.events.mark_implementation_started(req_id, "Model implementation started")

    def finish_batch(self, index: int, requirement_ids: list[str]) -> None:
        for req_id in requirement_ids:
            self.sdk.events.mark_implementation_done(req_id, "Model implementation complete; GUI unverified")
        if not self.sdk.git.commit(f"batch {index}: implement {len(requirement_ids)} requirements"):
            raise RuntimeError("ARC-Bench Git commit found no implementation changes")

    def fail_batch(self, requirement_ids: list[str], message: str) -> None:
        for req_id in requirement_ids:
            self.sdk.events.mark_implementation_failed(req_id, message[:500])

    def commit_repairs(self) -> None:
        self.sdk.git.commit("repair: pass local build and startup checks")

    def commit_failed_requirements(self) -> None:
        # A later successful batch may already have included these states.
        # Otherwise preserve the final FAILED projection in Git as well as in
        # the SDK event stream and independent production trace.
        self.sdk.git.commit("record failed requirement states")

    def complete(self, *, partial: bool = False) -> None:
        message = (
            "Partial implementation retained; failed requirements remain FAILED; "
            "local build/start passed and GUI evaluation is pending"
            if partial
            else "Local build/start contract passed; GUI evaluation pending"
        )
        self.sdk.events.mark_run_completed(message)

    def fail(self, message: str) -> None:
        self.sdk.events.mark_run_failed(message[:500])
