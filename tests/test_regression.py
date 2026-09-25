from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from factory26_harness.browser_probe import MAX_STEPS, validate_steps
from factory26_harness.regression import MAX_SUMMARY_CHARS, RegressionMemory
from factory26_harness.trace import ProductionTrace, verify_trace_rows


class RegressionMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.trace = ProductionTrace(self.root / "trace.jsonl")
        self.memory = RegressionMemory(self.trace)
        self.manifest = {"frontend/src/app.js": "source-a", "backend/server.mjs": "source-b"}
        # Every test replaces the module-level browser entry point. No test can
        # launch a browser, server, real model, or any evaluator test suite.
        self.probe = self.enterContext(patch(
            "factory26_harness.regression.probe_local_app",
            return_value={"ok": True, "behavioral_checks": 1, "behavioral_assertions": 1},
        ))
        self.source_manifest = self.enterContext(patch(
            "factory26_harness.regression.app_source_manifest", return_value=self.manifest
        ))

    @staticmethod
    def steps(label: str = "Save") -> list[dict]:
        return [{"action": "click", "role": "button", "name": label,
                 "expect_text": [f"Completed {label}"]}]

    def remember(self, label: str = "Save", requirements: list[str] | None = None) -> str:
        self.assertTrue(self.memory.remember(
            requirements if requirements is not None else ["REQ-1"],
            self.steps(label), self.manifest,
        ))
        return self.memory.summary()["capsule_ids"][-1]

    def rows(self) -> list[dict]:
        return [json.loads(line) for line in self.trace.path.read_text().splitlines()]

    def test_no_capsules_pass_explicitly_without_claiming_behavioral_coverage(self) -> None:
        for final in (False, True):
            result = self.memory.check(self.root, 3991, final=final)
            self.assertTrue(result.passed)
            self.assertIn("No coverage", result.summary)
            self.assertIn("no behavioral verification", result.summary)
        self.probe.assert_not_called()
        self.source_manifest.assert_not_called()
        summary = self.memory.summary()
        self.assertIs(type(summary["capsule_count"]), int)
        self.assertEqual(summary["capsule_count"], 0)
        self.assertEqual(len(summary["history"]), 2)
        for entry in summary["history"]:
            self.assertEqual(entry["status"], "no_coverage")
            self.assertEqual(entry["selected_ids"], [])
            self.assertEqual(entry["unselected_ids"], [])
            self.assertEqual(entry["results"], [])

    def test_rejects_empty_invalid_inspection_and_no_positive_assertion(self) -> None:
        invalid = [
            [], None, {}, [None], [{"action": "evaluate", "value": "1"}],
            [{"action": "navigate", "path": "https://example.com"}],
            [{"action": "reload", "expect_text": ["Ready"]}],
            [{"action": "navigate", "path": "/", "expect_text": ["Ready"]}],
            [{"action": "click", "text": "Save"}],
            [{"action": "click", "text": "Save", "expect_absent": ["Error"]}],
            [{"action": "click", "text": "Save", "expect_text": [""]}],
            [{"action": "click", "text": "Save", "expect_text": ["   "]}],
            [{"action": "click", "text": "Save", "expect_text": [True]}],
            [{"action": "click", "text": "Save", "expect_text": [42]}],
            [{"action": "click", "text": "Save", "expect_text": [{"ok": True}]}],
            [{"action": "click", "text": "Save", "expect_text": "Saved"}],
            [{"action": "fill", "label": "Name", "value": "", "expect_text": ["Saved"]}],
            self.steps() * (MAX_STEPS + 1),
        ]
        for steps in invalid:
            with self.subTest(steps=steps):
                self.assertFalse(self.memory.remember(["REQ-1"], steps, self.manifest))
        self.assertEqual(self.memory.summary()["capsule_count"], 0)
        self.assertEqual(self.memory.summary()["rejected_invalid_count"], len(invalid))
        self.probe.assert_not_called()

    def test_long_flow_replays_all_steps_and_keeps_final_assertion(self) -> None:
        steps = [{"action": "fill", "label": f"Field {index}", "value": "fixture"}
                 for index in range(9)] + [
            {"action": "click", "role": "button", "name": "Save", "expect_text": ["Saved"]},
            {"action": "reload", "expect_text": ["Saved"], "expect_absent": ["Error"]},
        ]
        self.assertTrue(self.memory.remember(["REQ-long-flow"], steps, self.manifest))
        self.assertTrue(self.memory.check(self.root, 3991, final=True).passed)
        replayed = self.probe.call_args.args[2]
        self.assertEqual(replayed, validate_steps(steps))
        self.assertEqual(len(replayed), 11)
        self.assertEqual(replayed[-1]["expect_text"], ["Saved"])
        self.probe.return_value = {"ok": False, "assertion_failures": [{"step": 11, "missing": ["Saved"]}]}
        self.assertFalse(self.memory.check(self.root, 3991, final=True).passed)

    def test_accepts_each_interaction_and_assertions_after_reload(self) -> None:
        for action in ("click", "fill", "press", "select", "check"):
            with self.subTest(action=action):
                step = {"action": action, "label": "Control"}
                if action in {"fill", "press", "select"}:
                    step["value"] = "Enter" if action == "press" else "Option"
                self.assertTrue(self.memory.remember([], [
                    step, {"action": "reload", "expect_text": ["Done"], "expect_absent": ["Error"]},
                ], self.manifest))
        self.assertEqual(self.memory.summary()["capsule_count"], 5)
        self.probe.assert_not_called()

    def test_uses_validator_and_rejects_invalid_metadata(self) -> None:
        with patch("factory26_harness.regression.validate_steps", wraps=validate_steps) as validate:
            self.remember()
            validate.assert_called_once()
        for requirements, manifest in (([None], {}), ("REQ-1", {}), ([" "], {}), ([], {"x": 1})):
            with self.subTest(requirements=requirements, manifest=manifest):
                self.assertFalse(self.memory.remember(requirements, self.steps(), manifest))

    def test_deep_copy_input_replay_and_report_cannot_mutate_capsule(self) -> None:
        steps = self.steps()
        expected = validate_steps(deepcopy(steps))
        requirements = ["REQ-original"]
        manifest = dict(self.manifest)
        self.assertTrue(self.memory.remember(requirements, steps, manifest))
        capsule_id = self.memory.summary()["capsule_ids"][0]
        steps[0]["expect_text"].append("Injected")
        steps[0]["name"] = "Changed"
        requirements[:] = ["REQ-changed"]
        manifest["frontend/src/app.js"] = "changed"
        self.assertFalse(self.memory.remember(["REQ-original"], expected, self.manifest))
        self.remember("Other", ["REQ-other"])

        def mutate(root, port, recipe):
            if recipe[0]["name"] == "Save":
                self.assertEqual(recipe, expected)
            recipe[0]["expect_text"].append("Probe mutation")
            return {"ok": True, "behavioral_checks": 1, "behavioral_assertions": 1}

        self.probe.side_effect = mutate
        for _ in range(2):
            self.assertTrue(self.memory.check(
                self.root, 3991, requirement_ids=("REQ-original",)
            ).passed)
            self.assertEqual(self.memory.history[-1]["selected_ids"][0], capsule_id)
        summary = self.memory.summary()
        summary["capsule_ids"].clear()
        summary["history"][0]["selected_ids"].clear()
        summary["history"][0]["results"][0]["status"] = "corrupted"
        self.memory.history.clear()
        self.assertEqual(self.memory.summary()["capsule_count"], 2)
        self.assertEqual(len(self.memory.history), 2)
        self.assertEqual(self.memory.history[0]["results"][0]["status"], "passed")

    def test_stable_hash_deduplicates_normalized_recipe_requirements_and_manifest(self) -> None:
        first = self.remember(requirements=["REQ-2", "REQ-1", "REQ-1"])
        self.assertFalse(self.memory.remember(
            ["REQ-1", "REQ-2"], validate_steps(self.steps()),
            dict(reversed(list(self.manifest.items()))),
        ))
        other = RegressionMemory(self.trace)
        self.assertTrue(other.remember(["REQ-1", "REQ-2"], self.steps(), self.manifest))
        self.assertEqual(other.summary()["capsule_ids"], [first])
        self.assertTrue(self.memory.remember(["REQ-1"], self.steps(), self.manifest))
        self.assertTrue(self.memory.remember(["REQ-1", "REQ-2"], self.steps("New"), self.manifest))
        self.assertTrue(self.memory.remember(
            ["REQ-1", "REQ-2"], self.steps(), {**self.manifest, "backend/server.mjs": "changed"}
        ))
        self.assertEqual(len(set(self.memory.summary()["capsule_ids"])), 4)
        self.assertEqual(self.memory.summary()["duplicate_count"], 1)

    def test_stored_event_seals_normalized_recoverable_recipe_without_stdout_body(self) -> None:
        self.trace.stdout_progress = True
        steps = self.steps("PRIVATE RECIPE MARKER")
        steps[0]["ignored_metadata"] = {"note": "not part of the recipe"}
        expected = validate_steps(deepcopy(steps))
        requirements = ["REQ-2", "REQ-1", "REQ-1"]
        manifest = dict(self.manifest)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertTrue(self.memory.remember(requirements, steps, manifest))
        self.assertNotIn("PRIVATE RECIPE MARKER", output.getvalue())
        self.assertNotIn('"steps"', output.getvalue())
        steps[0]["expect_text"].append("Changed by caller")
        requirements.clear()
        manifest.clear()
        rows = self.rows()
        stored = [row for row in rows if row["event"] == "regression_capsule_stored"]
        self.assertEqual(len(stored), 1)
        event = stored[0]["payload"]
        self.assertEqual(event["steps"], expected)
        self.assertEqual(event["requirement_ids"], ["REQ-1", "REQ-2"])
        self.assertEqual(set(event), {
            "capsule_id", "requirement_ids", "steps", "origin_source_manifest_digest",
        })
        origin = hashlib.sha256(json.dumps(
            self.manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")).hexdigest()
        self.assertEqual(event["origin_source_manifest_digest"], origin)
        restored_id = hashlib.sha256(json.dumps({
            "recipe": event["steps"], "requirement_ids": event["requirement_ids"],
            "origin_source_manifest_digest": event["origin_source_manifest_digest"],
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()
        self.assertEqual(restored_id, event["capsule_id"])
        self.assertEqual(self.memory.summary()["capsule_ids"], [restored_id])
        self.assertTrue(verify_trace_rows(rows, require_fully_sealed=True)["valid"])
        event["steps"][0]["expect_text"].append("Tampered evidence")
        self.assertFalse(verify_trace_rows(rows, require_fully_sealed=True)["valid"])

    def test_stored_trace_payload_cannot_mutate_memory_and_rejections_do_not_emit_it(self) -> None:
        self.memory = RegressionMemory(self.trace, maximum_capsules=1)
        with patch.object(self.trace, "record", wraps=self.trace.record) as record:
            capsule_id = self.remember(requirements=["REQ-original"])
        payload = next(
            call.kwargs for call in record.call_args_list
            if call.args == ("regression_capsule_stored",)
        )
        payload["steps"][0]["expect_text"].append("Trace consumer mutation")
        payload["requirement_ids"].clear()
        self.assertFalse(self.memory.remember(["REQ-original"], self.steps(), self.manifest))
        self.assertFalse(self.memory.remember([], [], self.manifest))
        self.assertFalse(self.memory.remember([], self.steps("Capacity overflow"), self.manifest))
        self.assertTrue(self.memory.check(self.root, 3991).passed)
        self.assertEqual(self.probe.call_args.args[2], validate_steps(self.steps()))
        stored = [row for row in self.rows() if row["event"] == "regression_capsule_stored"]
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["payload"]["capsule_id"], capsule_id)
        self.assertEqual(stored[0]["payload"]["requirement_ids"], ["REQ-original"])
        self.assertEqual(stored[0]["payload"]["steps"], validate_steps(self.steps()))
        self.assertNotIn("steps", json.dumps(self.memory.summary()))
        self.assertTrue(verify_trace_rows(self.rows(), require_fully_sealed=True)["valid"])

    def test_full_capacity_explicitly_rejects_without_replacing_or_eviction(self) -> None:
        self.memory = RegressionMemory(self.trace, maximum_capsules=2)
        kept = [self.remember("First"), self.remember("Second")]
        self.assertFalse(self.memory.remember(["REQ-1"], self.steps("Third"), self.manifest))
        self.assertFalse(self.memory.remember(["REQ-1"], self.steps("First"), self.manifest))
        summary = self.memory.summary()
        self.assertEqual(summary["capsule_ids"], kept)
        self.assertEqual(summary["rejected_capacity_count"], 1)
        self.assertEqual(summary["duplicate_count"], 1)
        self.assertEqual(summary["remember_history"][-2]["status"], "rejected_capacity")
        self.assertEqual(self.rows()[-2]["payload"]["status"], "rejected_capacity")
        self.assertTrue(self.memory.check(self.root, 3991, final=True).passed)
        self.assertEqual(self.memory.history[-1]["selected_ids"], kept)

    def test_zero_and_invalid_capacity(self) -> None:
        disabled = RegressionMemory(self.trace, maximum_capsules=0)
        self.assertFalse(disabled.remember([], self.steps(), self.manifest))
        self.assertEqual(disabled.summary()["rejected_capacity_count"], 1)
        for maximum in (-1, True, 1.5, "2"):
            with self.subTest(maximum=maximum), self.assertRaises(ValueError):
                RegressionMemory(self.trace, maximum_capsules=maximum)

    def test_priority_reserves_fair_slot_even_with_many_matching_capsules(self) -> None:
        # The matching capsules are deliberately ahead of the unrelated ones.
        priority = {self.remember(f"Priority {index}", ["REQ-hot"]) for index in range(3)}
        others = {self.remember(f"Other {index}", ["REQ-cold"]) for index in range(4)}
        all_ids = priority | others
        seen = set()
        for _ in range(len(all_ids)):
            before = self.probe.call_count
            self.assertTrue(self.memory.check(self.root, 3991, requirement_ids=("REQ-hot",)).passed)
            entry = self.memory.history[-1]
            self.assertEqual(self.probe.call_count - before, 2)
            self.assertIn(entry["selected_ids"][0], priority)
            self.assertEqual(len(set(entry["selected_ids"])), 2)
            self.assertEqual(set(entry["unselected_ids"]), all_ids - set(entry["selected_ids"]))
            seen.update(entry["selected_ids"])
        self.assertEqual(seen, all_ids)

    def test_unmatched_rotation_and_final_replay_all_in_separate_calls(self) -> None:
        stored = [self.remember(str(index), [f"REQ-{index}"]) for index in range(5)]
        for _ in range(3):
            self.assertTrue(self.memory.check(self.root, 3991, requirement_ids=("REQ-none",)).passed)
        selected = [entry["selected_ids"] for entry in self.memory.history]
        self.assertEqual(selected[0], stored[:2])
        self.assertEqual(selected[1], stored[2:4])
        self.assertIn(stored[4], selected[2])
        self.probe.reset_mock()
        self.assertTrue(self.memory.check(self.root, 3991, final=True).passed)
        self.assertEqual(self.probe.call_count, 5)
        self.assertEqual(self.memory.history[-1]["selected_ids"], stored)
        self.assertEqual(self.memory.history[-1]["unselected_ids"], [])
        for call in self.probe.call_args_list:
            self.assertEqual(call.args[:2], (self.root, 3991))
            self.assertEqual(len(call.args[2]), 1)
        self.assertEqual(len({id(call.args[2]) for call in self.probe.call_args_list}), 5)

    def test_false_empty_and_nonbehavioral_probe_results_fail_without_collecting(self) -> None:
        self.remember()
        invalid = [
            {"ok": False, "behavioral_checks": 1, "behavioral_assertions": 1},
            {"ok": True, "behavioral_checks": 0, "behavioral_assertions": 1},
            {"ok": True, "behavioral_checks": 1, "behavioral_assertions": 0},
            {"ok": True}, {}, None,
            {"ok": "true", "behavioral_checks": 1, "behavioral_assertions": 1},
        ]
        for field in ("behavioral_checks", "behavioral_assertions"):
            for count in (-1, True, "1", None, 1.5):
                invalid.append({"ok": True, "behavioral_checks": 1, "behavioral_assertions": 1,
                                field: count})
        for result in invalid:
            with self.subTest(result=result):
                self.probe.return_value = result
                check = self.memory.check(self.root, 3991)
                self.assertFalse(check.passed)
                self.assertIn("steps=", check.summary)
                self.assertIn("error=", check.summary)
                self.assertEqual(self.memory.summary()["capsule_count"], 1)
                self.assertEqual(len(self.memory.summary()["remember_history"]), 1)

    def test_first_failure_is_not_overwritten_by_later_success(self) -> None:
        ids = [self.remember("First"), self.remember("Second"), self.remember("Third")]
        self.probe.side_effect = [
            {"ok": False, "behavioral_checks": 1, "behavioral_assertions": 1,
             "assertion_failures": [{"step": 1, "missing": ["Completed First"]}]},
            {"ok": True, "behavioral_checks": 1, "behavioral_assertions": 1},
            {"ok": True, "behavioral_checks": 1, "behavioral_assertions": 1},
        ]
        result = self.memory.check(self.root, 3991, final=True)
        self.assertFalse(result.passed)
        self.assertEqual(self.probe.call_count, 3)
        self.assertIn("Completed First", result.summary)
        self.assertIn('"action":"click"', result.summary)
        self.assertEqual(self.memory.history[-1]["failed_ids"], ids[:1])
        self.assertEqual([row["status"] for row in self.memory.history[-1]["results"]],
                         ["failed", "passed", "passed"])
        # A repaired later check may pass, but must preserve the failed evidence.
        self.probe.side_effect = None
        self.assertTrue(self.memory.check(self.root, 3991, final=True).passed)
        self.assertEqual(self.memory.summary()["failed_check_count"], 1)
        self.assertEqual(self.memory.history[0]["status"], "failed")
        self.assertEqual(self.memory.history[1]["status"], "passed")

    def test_exception_is_failure_and_does_not_stop_remaining_replays(self) -> None:
        self.remember("First")
        self.remember("Second")
        self.probe.side_effect = [RuntimeError("Control Save is unavailable"),
                                 {"ok": True, "behavioral_checks": 1, "behavioral_assertions": 1}]
        result = self.memory.check(self.root, 3991)
        self.assertFalse(result.passed)
        self.assertIn("RuntimeError: Control Save is unavailable", result.summary)
        self.assertIn("steps=", result.summary)
        self.assertEqual(self.probe.call_count, 2)

    def test_error_summary_is_bounded_but_contains_recipe_and_error(self) -> None:
        for index in range(5):
            self.remember(str(index))
        self.probe.return_value = {
            "ok": False, "behavioral_checks": 1, "behavioral_assertions": 1,
            "page_errors": ["Missing control " + "x" * 50_000],
            "observations": [{"visible_text": "never include whole page text"}],
        }
        result = self.memory.check(self.root, 3991, final=True)
        self.assertFalse(result.passed)
        self.assertLessEqual(len(result.summary), MAX_SUMMARY_CHARS)
        self.assertIn("Missing control", result.summary)
        self.assertIn("steps=", result.summary)
        self.assertIn("3 additional failures", result.summary)
        self.assertNotIn("never include whole page text", result.summary)
        self.assertEqual(len(self.memory.history[-1]["failed_ids"]), 5)

    def test_trace_and_history_record_selection_results_and_source_digest(self) -> None:
        ids = [self.remember(str(index)) for index in range(3)]
        self.assertTrue(self.memory.check(self.root, 3991).passed)
        entry = self.memory.history[-1]
        self.assertEqual(entry["selected_ids"], ids[:2])
        self.assertEqual(entry["unselected_ids"], ids[2:])
        self.assertEqual(len(entry["results"]), 2)
        origin = entry["results"][0]["origin_source_manifest_digest"]
        self.assertEqual(entry["source_manifest_digest"], origin)
        # Changes to current source are expected; the origin remains frozen.
        self.source_manifest.return_value = {"frontend/src/app.js": "new revision"}
        self.assertTrue(self.memory.check(self.root, 3991, final=True).passed)
        self.assertNotEqual(self.memory.history[-1]["source_manifest_digest"], origin)
        self.assertEqual(self.memory.history[-1]["results"][0]["origin_source_manifest_digest"], origin)
        rows = self.rows()
        self.assertTrue(verify_trace_rows(rows, require_fully_sealed=True)["valid"])
        checks = [row["payload"] for row in rows if row["payload"].get("phase") == "completed"]
        self.assertEqual(len(checks), 2)
        for row, history in zip(checks, self.memory.history):
            self.assertEqual(row["selected_ids"], history["selected_ids"])
            self.assertEqual(row["unselected_ids"], history["unselected_ids"])
            self.assertEqual(row["results"], history["results"])
        encoded = json.dumps(self.memory.summary())
        for forbidden in ("Completed 0", "steps", "observations", "passed_requirements"):
            self.assertNotIn(forbidden, encoded)
        self.assertEqual(self.memory.summary()["requirement_coverage"], "not_assessed")

    def test_manifest_exception_fails_with_unrun_capsules_recorded(self) -> None:
        ids = [self.remember(str(index)) for index in range(3)]
        self.source_manifest.side_effect = RuntimeError("source input unreadable")
        result = self.memory.check(self.root, 3991)
        self.assertFalse(result.passed)
        self.assertIn("source input unreadable", result.summary)
        self.assertIn("steps=", result.summary)
        self.probe.assert_not_called()
        entry = self.memory.history[-1]
        self.assertEqual(entry["selected_ids"], ids[:2])
        self.assertEqual(entry["unselected_ids"], ids[2:])
        self.assertEqual([item["status"] for item in entry["results"]], ["not_run", "not_run"])


if __name__ == "__main__":
    unittest.main()
