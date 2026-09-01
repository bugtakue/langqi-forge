from __future__ import annotations

import hashlib
import json
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory26_harness.checks import (
    frontend_build_check,
    interaction_policy_check,
    package_policy_check,
)
from factory26_harness.cli import _safe_smoke_port
from factory26_harness.impact import ChangeImpactGraph
from factory26_harness.trace import (
    ProductionTrace,
    find_unredacted_secrets,
    redact_sensitive_data,
    verify_trace_rows,
)
from factory26_harness.workspace_tools import WorkspaceTools


class ToolAndTraceTests(unittest.TestCase):
    def test_batch_read_returns_multiple_hash_bound_files_in_one_tool_call(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frontend = root / "frontend"
            backend = root / "backend"
            frontend.mkdir()
            backend.mkdir()
            (frontend / "app.js").write_text("const ready = true;\n", encoding="utf-8")
            (backend / "server.mjs").write_text(
                "export const port = 1;\n", encoding="utf-8"
            )
            tools = WorkspaceTools(
                root, ProductionTrace(root / ".arc" / "trace.jsonl"), 3910
            )

            result = json.loads(
                tools.execute(
                    "read_files",
                    {"paths": ["frontend/app.js", "backend/server.mjs"]},
                )
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["file_count"], 2)
            self.assertEqual(
                [entry["path"] for entry in result["files"]],
                ["frontend/app.js", "backend/server.mjs"],
            )
            self.assertEqual(
                result["files"][0]["sha256"],
                hashlib.sha256(b"const ready = true;\n").hexdigest(),
            )
            duplicate = json.loads(
                tools.execute(
                    "read_files",
                    {"paths": ["frontend/app.js", "frontend/./app.js"]},
                )
            )
            self.assertFalse(duplicate["ok"])

    def test_smoke_port_selection_skips_occupied_and_grading_ports(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
            occupied.bind(("127.0.0.1", 0))
            start = occupied.getsockname()[1]
            selected = _safe_smoke_port(start, start + 1)
        self.assertNotIn(selected, {start, start + 1})

    def test_writes_are_scoped_and_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = ProductionTrace(root / ".arc" / "trace.jsonl")
            tools = WorkspaceTools(root, trace, smoke_port=3911)
            ok = json.loads(
                tools.execute(
                    "write_file", {"path": "frontend/src/app.js", "content": "ok\n"}
                )
            )
            denied = json.loads(
                tools.execute("write_file", {"path": "../escape.txt", "content": "bad"})
            )
            self.assertTrue(ok["ok"])
            self.assertFalse(denied["ok"])
            self.assertEqual(tools.changed_files, {"frontend/src/app.js"})

    def test_trace_redacts_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            ProductionTrace(path).record(
                "request",
                api_key="secret",
                nested={"Authorization": "Bearer secret"},
                password="hunter2",
                headers={"X-API-Key": "header-secret-value"},
                cookie="session=raw-cookie-value",
                raw=(
                    "OPENAI_API_KEY=top-secret-value Bearer abcdefghijklmnop "
                    "DATABASE_PASSWORD=hunter2 X-API-Key: header-secret-value "
                    "Cookie: session=raw-cookie-value; Path=/ "
                    "postgresql://app:db-secret@db.example.test/app"
                ),
            )
            row = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(row["payload"]["api_key"], "[REDACTED]")
            self.assertEqual(row["payload"]["nested"]["Authorization"], "[REDACTED]")
            self.assertEqual(row["payload"]["password"], "[REDACTED]")
            self.assertEqual(row["payload"]["headers"], "[REDACTED]")
            self.assertEqual(row["payload"]["cookie"], "[REDACTED]")
            self.assertNotIn("top-secret-value", row["payload"]["raw"])
            self.assertNotIn("abcdefghijklmnop", row["payload"]["raw"])
            self.assertNotIn("hunter2", row["payload"]["raw"])
            self.assertNotIn("header-secret-value", row["payload"]["raw"])
            self.assertNotIn("raw-cookie-value", row["payload"]["raw"])
            self.assertNotIn("db-secret", row["payload"]["raw"])
            self.assertEqual(find_unredacted_secrets(row), [])

    def test_redaction_preserves_basic_prose_but_removes_basic_auth(self) -> None:
        prose = (
            "Enterprise capability may be unnecessary for basic spreadsheet workflows"
        )
        self.assertEqual(redact_sensitive_data(prose), prose)
        rendered = redact_sensitive_data("Authorization: Basic YWRtaW46c2VjcmV0")
        self.assertNotIn("YWRtaW46c2VjcmV0", rendered)
        self.assertIn("[REDACTED]", rendered)

    def test_release_artifact_redaction_matches_trace_projection(self) -> None:
        report = {
            "planner_contract": {
                "risks": [
                    "basic spreadsheet workflows",
                    "Authorization: Basic YWRtaW46c2VjcmV0",
                ]
            }
        }
        projected = redact_sensitive_data(report)
        self.assertEqual(
            projected["planner_contract"]["risks"][0],
            "basic spreadsheet workflows",
        )
        self.assertNotIn(
            "YWRtaW46c2VjcmV0",
            projected["planner_contract"]["risks"][1],
        )

    def test_trace_is_hash_chained_and_tampering_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            trace = ProductionTrace(path)
            trace.record("first", value=1)
            trace.record("second", value=2)
            rows = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            ]
            verified = verify_trace_rows(rows)
            self.assertTrue(verified["valid"], verified)
            self.assertEqual(verified["sealed_rows"], 2)
            self.assertEqual(rows[1]["previous_hash"], rows[0]["hash"])
            rows[0]["payload"]["value"] = 99
            self.assertFalse(verify_trace_rows(rows)["valid"])

    def test_release_verification_rejects_unsealed_and_mixed_traces(self) -> None:
        legacy = [{"sequence": 1, "event": "legacy", "payload": {}}]
        self.assertTrue(verify_trace_rows(legacy)["valid"])
        strict = verify_trace_rows(legacy, require_fully_sealed=True)
        self.assertFalse(strict["valid"])
        self.assertEqual(strict["reason"], "unsealed trace row")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            path.write_text(json.dumps(legacy[0]) + "\n", encoding="utf-8")
            ProductionTrace(path).record("sealed", value=1)
            rows = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertTrue(verify_trace_rows(rows)["valid"])
            self.assertFalse(
                verify_trace_rows(rows, require_fully_sealed=True)["valid"]
            )

    def test_existing_file_overwrite_requires_matching_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "frontend" / "src" / "app.js"
            target.parent.mkdir(parents=True)
            target.write_text("before\n", encoding="utf-8")
            tools = WorkspaceTools(
                root, ProductionTrace(root / ".arc" / "trace.jsonl"), 3912
            )
            missing = json.loads(
                tools.execute(
                    "write_file", {"path": "frontend/src/app.js", "content": "after\n"}
                )
            )
            stale = json.loads(
                tools.execute(
                    "write_file",
                    {
                        "path": "frontend/src/app.js",
                        "content": "after\n",
                        "expected_sha256": "0" * 64,
                    },
                )
            )
            valid = json.loads(
                tools.execute(
                    "write_file",
                    {
                        "path": "frontend/src/app.js",
                        "content": "after\n",
                        "expected_sha256": hashlib.sha256(b"before\n").hexdigest(),
                    },
                )
            )
            self.assertFalse(missing["ok"])
            self.assertFalse(stale["ok"])
            self.assertTrue(valid["ok"])
            self.assertEqual(target.read_text(encoding="utf-8"), "after\n")

    def test_secret_files_and_write_budget_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "backend").mkdir()
            (root / "backend" / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {"FACTORY26_MAX_CHANGED_FILES": "1", "FACTORY26_MAX_WRITE_BYTES": "8"},
            ):
                tools = WorkspaceTools(
                    root, ProductionTrace(root / ".arc" / "trace.jsonl"), 3913
                )
            secret = json.loads(tools.execute("read_file", {"path": "backend/.env"}))
            first = json.loads(
                tools.execute(
                    "write_file", {"path": "frontend/a.js", "content": "12345678"}
                )
            )
            second = json.loads(
                tools.execute("write_file", {"path": "frontend/b.js", "content": "x"})
            )
            self.assertFalse(secret["ok"])
            self.assertTrue(first["ok"])
            self.assertFalse(second["ok"])

    def test_control_files_case_variants_symlinks_and_control_paths_are_denied(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            (root / "backend").mkdir()
            (root / "frontend").mkdir()
            (root / ".arc").mkdir()
            (root / "backend" / ".ENV.PRODUCTION").write_text("TOKEN=secret")
            (root / ".arc" / "harness-report.json").write_text("{}")
            external = Path(outside) / "outside.txt"
            external.write_text("outside")
            (root / "frontend" / "escape").symlink_to(external)
            tools = WorkspaceTools(
                root, ProductionTrace(root / ".arc-trace" / "trace.jsonl"), 3915
            )
            for path in (
                "backend/.ENV.PRODUCTION",
                ".arc/harness-report.json",
                "frontend/escape",
                "frontend/bad\nname.js",
            ):
                result = json.loads(tools.execute("read_file", {"path": path}))
                self.assertFalse(result["ok"], path)

    def test_large_tool_results_remain_valid_json_and_noop_writes_do_not_count(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "frontend" / "large.txt"
            target.parent.mkdir(parents=True)
            content = "".join(
                f"{index:04d} " + "x" * 100 + "\n" for index in range(500)
            )
            target.write_text(content, encoding="utf-8")
            tools = WorkspaceTools(
                root, ProductionTrace(root / ".trace" / "trace.jsonl"), 3916
            )
            result = json.loads(
                tools.execute("read_file", {"path": "frontend/large.txt"})
            )
            self.assertTrue(result["ok"])
            self.assertTrue(result["truncated"])

            digest = hashlib.sha256(content.encode()).hexdigest()
            no_change = json.loads(
                tools.execute(
                    "write_file",
                    {
                        "path": "frontend/large.txt",
                        "content": content,
                        "expected_sha256": digest,
                    },
                )
            )
            self.assertTrue(no_change["ok"])
            self.assertFalse(no_change["changed"])
            self.assertEqual(tools.change_revision, 0)
            self.assertEqual(tools.changed_files, set())

    def test_validation_subprocess_does_not_receive_model_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frontend = root / "frontend"
            frontend.mkdir()
            (frontend / "package.json").write_text(
                json.dumps(
                    {
                        "name": "safe-env-test",
                        "private": True,
                        "scripts": {"build": "node build.mjs"},
                    }
                ),
                encoding="utf-8",
            )
            (frontend / "build.mjs").write_text(
                "import { writeFileSync } from 'node:fs';\n"
                "writeFileSync('observed.txt', process.env.OPENAI_API_KEY || 'missing');\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"OPENAI_API_KEY": "must-not-reach-build"}):
                result = frontend_build_check(root)
            self.assertTrue(result.passed, result.summary)
            self.assertEqual((frontend / "observed.txt").read_text(), "missing")

    def test_package_policy_rejects_lifecycle_hooks_and_local_dependencies(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, script in (("frontend", "build"), ("backend", "start")):
                target = root / name
                target.mkdir()
                package = {
                    "name": name,
                    "private": True,
                    "scripts": {script: "node app.mjs"},
                }
                if name == "frontend":
                    package["scripts"]["postinstall"] = "node steal.mjs"
                    package["dependencies"] = {"escape": "file:../../outside"}
                (target / "package.json").write_text(json.dumps(package))
            result = package_policy_check(root)
            self.assertFalse(result.passed)
            self.assertIn("postinstall", result.summary)
            self.assertIn("unsafe dependency", result.summary)

    def test_interaction_policy_requires_in_page_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "frontend" / "src"
            source.mkdir(parents=True)
            app = source / "app.js"
            app.write_text(
                'card.querySelector("[role=alert]").textContent = message;\n',
                encoding="utf-8",
            )
            self.assertTrue(interaction_policy_check(root).passed)

            app.write_text(
                'window.alert("Reviewer must differ from requester");\n'
                'globalThis.confirm("Continue?");\n',
                encoding="utf-8",
            )
            result = interaction_policy_check(root)
            self.assertFalse(result.passed)
            self.assertIn("frontend/src/app.js:1", result.summary)
            self.assertIn("frontend/src/app.js:2", result.summary)
            self.assertIn("owning semantic DOM container", result.summary)

    def test_write_invalidates_previous_validation_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "frontend").mkdir()
            (root / "backend").mkdir()
            (root / "frontend" / "package.json").write_text(
                json.dumps(
                    {
                        "name": "frontend",
                        "private": True,
                        "scripts": {"build": 'node -e ""'},
                    }
                ),
                encoding="utf-8",
            )
            (root / "backend" / "package.json").write_text(
                json.dumps(
                    {
                        "name": "backend",
                        "private": True,
                        "scripts": {"start": 'node -e ""'},
                    }
                ),
                encoding="utf-8",
            )
            tools = WorkspaceTools(
                root, ProductionTrace(root / ".arc" / "trace.jsonl"), 3914
            )
            tools.execute("write_file", {"path": "frontend/new.js", "content": "one\n"})
            validation = json.loads(tools.execute("run_validation", {"scope": "quick"}))
            self.assertTrue(validation["current_changes_validated"])
            tools.execute(
                "replace_text",
                {
                    "path": "frontend/new.js",
                    "old": "one",
                    "new": "two",
                    "expected_count": 1,
                },
            )
            self.assertFalse(tools.current_changes_validated)

    def test_impact_graph_uses_observed_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            graph = ChangeImpactGraph(Path(directory) / "impact.json")
            graph.record_requirement_files(["R1"], ["frontend/src/app.js"])
            graph.record_requirement_files(["R2"], ["backend/server.mjs"])
            self.assertEqual(
                graph.files_for_requirements(["R2", "R1"]),
                ["backend/server.mjs", "frontend/src/app.js"],
            )


if __name__ == "__main__":
    unittest.main()
