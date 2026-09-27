"""Optional adapter to the official ARC-Bench runtime SDK (events, traceability, git)."""

from __future__ import annotations

import os
from pathlib import Path


class ArcRuntime:
    def __init__(self, sdk, log) -> None:
        self.sdk = sdk
        self.log = log

    @classmethod
    def connect(cls, project_dir: Path, log):
        try:
            from arcbench_agent_runtime import AgentRuntime  # type: ignore
        except Exception as exc:  # noqa: BLE001
            if os.environ.get("ARCBENCH_RUNNER_EVENTS_PATH"):
                log(f"ARC runtime SDK unavailable: {exc}")
            return None
        try:
            return cls(AgentRuntime.from_env(project_dir=str(project_dir)), log)
        except Exception as exc:  # noqa: BLE001
            log(f"ARC runtime init failed: {exc}")
            return None

    def _safe(self, fn, *a, **k):
        try:
            return fn(*a, **k)
        except Exception as exc:  # noqa: BLE001
            self.log(f"ARC runtime call failed: {exc}")
            return None

    def start(self, tree: dict) -> None:
        self._safe(self.sdk.events.mark_run_started, "Forge agent run started")
        self._safe(self.sdk.traceability.init_db)
        self._safe(self.sdk.traceability.store_requirement_tree, tree)
        self._safe(self.sdk.git.ensure_repo, create_initial_commit=True)

    def impl_started(self, ids) -> None:
        for i in ids:
            self._safe(self.sdk.events.mark_implementation_started, i, "Implementation started")

    def impl_done(self, ids, msg="Implemented") -> None:
        for i in ids:
            self._safe(self.sdk.events.mark_implementation_done, i, msg)

    def impl_failed(self, ids, msg) -> None:
        for i in ids:
            self._safe(self.sdk.events.mark_implementation_failed, i, msg[:400])

    def test_result(self, rid: str, ok: bool, msg: str) -> None:
        fn = self.sdk.events.mark_test_passed if ok else self.sdk.events.mark_test_failed
        self._safe(fn, rid, msg[:400])

    def commit(self, message: str) -> None:
        self._safe(self.sdk.git.commit, message)

    def complete(self, msg: str) -> None:
        self._safe(self.sdk.events.mark_run_completed, msg)

    def fail(self, msg: str) -> None:
        self._safe(self.sdk.events.mark_run_failed, msg[:400])
