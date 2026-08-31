from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from factory26_harness.artifacts import (
    application_source_manifest,
    canonical_json,
    sha256_bytes,
    sha256_file,
    write_run_envelope,
)
from factory26_harness.capabilities import analyze_coverage
from factory26_harness.capability_memory import (
    forge_capability_capsule,
    match_capability_capsule,
    verify_capability_capsule,
)
from factory26_harness.requirements import RequirementNode
from factory26_harness.trace import ProductionTrace


def requirement(req_id: str, name: str) -> RequirementNode:
    return RequirementNode(
        req_id=req_id,
        name=name,
        description="",
        dependencies=(),
        scenarios=(),
        visual_reference=(),
        raw={},
    )


class CapabilityMemoryTests(unittest.TestCase):
    def _project(self, root: Path) -> tuple[Path, dict]:
        for relative in ("frontend/src/app.js", "backend/server.mjs"):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"// {relative}\n", encoding="utf-8")
        arc = root / ".arc"
        arc.mkdir()
        run_id = "11111111-1111-4111-8111-111111111111"
        source = application_source_manifest(root)
        coverage = analyze_coverage(
            [requirement("R1", "List and search repositories")], "github"
        ).as_dict()
        contract = {
            "domain": "github",
            "kernel_eligible": True,
            "capability_tags": ["repository_lifecycle"],
            "risks": ["permissions"],
            "validation_focus": ["persistence"],
            "rationale": "covered",
            "uncovered_requirement_ids": [],
            "decision_mode": "tool_call",
            "iterations": 1,
        }
        report = {
            "version": 2,
            "run_id": run_id,
            "requirement_sha256": "r" * 64,
            "source_identity": {"revision": "abc", "worktree_clean": True},
            "application_source": source,
            "capability_coverage": coverage,
            "planner_contract": contract,
        }
        (arc / "harness-report.json").write_text(json.dumps(report), encoding="utf-8")
        (arc / "planner-contract.json").write_text(
            json.dumps({"run_id": run_id, "contract": contract}), encoding="utf-8"
        )
        (arc / "compiled-plan.json").write_text(
            json.dumps({"run_id": run_id, "capability_coverage": coverage}),
            encoding="utf-8",
        )
        ProductionTrace(arc / "production-trace.jsonl").record(
            "run_completed", report=report
        )
        write_run_envelope(root)
        return root, report

    def _evaluation(self, root: Path, report: dict, label: str, profile: str) -> None:
        public = root / ".arc" / "public-eval"
        public.mkdir(exist_ok=True)
        raw_path = public / f"{label}.playwright.json"
        raw = {
            "stats": {
                "expected": 3,
                "unexpected": 0,
                "skipped": 0,
                "flaky": 0,
            },
            "suites": [],
        }
        raw_path.write_text(json.dumps(raw), encoding="utf-8")
        feedback = {
            "version": 2,
            "source_run_id": report["run_id"],
            "task_id": "github",
            "run_label": label,
            "fixture_profile": profile,
            "exit_code": 0,
            "failure_count": 0,
            "stats": raw["stats"],
            "application_source_sha256": report["application_source"]["sha256"],
            "test_bundle_sha256": "t" * 64,
            "playwright_report_sha256": sha256_file(raw_path),
        }
        feedback_path = public / f"{label}.feedback.json"
        feedback_path.write_text(json.dumps(feedback), encoding="utf-8")
        ProductionTrace(root / ".arc" / "production-trace.jsonl").record(
            "public_evaluation_completed",
            run_label=label,
            evidence_sha256=sha256_file(feedback_path),
            playwright_report_sha256=feedback["playwright_report_sha256"],
            application_source_sha256=feedback["application_source_sha256"],
            test_bundle_sha256=feedback["test_bundle_sha256"],
        )
        write_run_envelope(root)

    def test_capsule_requires_metamorphic_profiles_then_matches_semantic_variant(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, report = self._project(Path(temporary))
            self._evaluation(root, report, "github", "baseline")
            self.assertIsNone(forge_capability_capsule(root))
            self._evaluation(root, report, "github.adversarial", "adversarial")
            capsule = forge_capability_capsule(root)
            self.assertIsNotNone(capsule)
            verified = verify_capability_capsule(
                root / ".arc" / "capability-capsule.json"
            )
            variant = analyze_coverage(
                [requirement("RENAMED-9", "Locate and browse repositories")],
                "github",
            )
            matched = match_capability_capsule(verified, variant)
            self.assertTrue(matched["matched"], matched)
            self.assertTrue(matched["revalidation_required"])

            unsupported = analyze_coverage(
                [requirement("NEW-1", "Create a repository and deploy it to Kubernetes")],
                "github",
            )
            self.assertFalse(
                match_capability_capsule(verified, unsupported)["matched"]
            )

    def test_capsule_content_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, report = self._project(Path(temporary))
            self._evaluation(root, report, "github", "baseline")
            self._evaluation(root, report, "github.adversarial", "adversarial")
            forge_capability_capsule(root)
            path = root / ".arc" / "capability-capsule.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["reuse_policy"]["skips_revalidation"] = True
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "id does not match"):
                verify_capability_capsule(path)

    def test_rehashed_capsule_cannot_weaken_capability_or_profile_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, report = self._project(Path(temporary))
            self._evaluation(root, report, "github", "baseline")
            self._evaluation(root, report, "github.adversarial", "adversarial")
            forge_capability_capsule(root)
            path = root / ".arc" / "capability-capsule.json"
            original = json.loads(path.read_text(encoding="utf-8"))
            payload = json.loads(json.dumps(original))
            payload["capabilities"][0]["exclusions"] = []
            unsigned = {key: value for key, value in payload.items() if key != "capsule_id"}
            payload["capsule_id"] = sha256_bytes(canonical_json(unsigned))
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "stale or unknown"):
                verify_capability_capsule(path)

            payload = json.loads(json.dumps(original))
            payload["promotion_gate"]["required_profiles"] = []
            unsigned = {key: value for key, value in payload.items() if key != "capsule_id"}
            payload["capsule_id"] = sha256_bytes(canonical_json(unsigned))
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "promotion gate"):
                verify_capability_capsule(path)


if __name__ == "__main__":
    unittest.main()
