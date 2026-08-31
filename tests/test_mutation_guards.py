from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "factory26_harness"
    / "templates"
    / "sheet"
    / "backend"
    / "compute.mjs"
)
SUITE = ROOT / "tests" / "compute_kernel.test.mjs"
ENTERPRISE_SOURCE = (
    ROOT
    / "factory26_harness"
    / "templates"
    / "github"
    / "backend"
    / "enterprise.mjs"
)
ENTERPRISE_SUITE = ROOT / "tests" / "enterprise_kernel.test.mjs"


class MutationGuardTests(unittest.TestCase):
    def test_compute_contract_suite_kills_critical_invariant_mutants(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        mutants = {
            "accept_unbalanced_journal": (
                "if (debitCents !== creditCents) throw new Error",
                "if (false && debitCents !== creditCents) throw new Error",
            ),
            "disable_bom_cycle_guard": (
                "if (visiting.has(itemId)) throw new Error",
                "if (false && visiting.has(itemId)) throw new Error",
            ),
            "break_formula_multiplication": (
                'value = operator === "*" ? value * right : value / right;',
                'value = operator === "*" ? value + right : value / right;',
            ),
            "erase_mrp_net_requirements": (
                "const netRequirement = Math.max(0, roundQuantity(event.quantity - usable));",
                "const netRequirement = 0;",
            ),
            "ignore_compute_event_tampering": (
                'if (hash(unsigned) !== eventHash) return { valid: false, brokenAt: index + 1, reason: "event_hash_mismatch" };',
                'if (false && hash(unsigned) !== eventHash) return { valid: false, brokenAt: index + 1, reason: "event_hash_mismatch" };',
            ),
            "ignore_journal_tampering": (
                "if (journal.sequence !== index + 1 || hash(unsigned) !== journalHash) {",
                "if (journal.sequence !== index + 1) {",
            ),
            "continue_after_compute_integrity_failure": (
                'if (!integrity.valid) return fail("integrity", `enterprise state integrity failed: ${integrity.layer || integrity.reason}`, integrity);',
                'if (false && !integrity.valid) return fail("integrity", `enterprise state integrity failed: ${integrity.layer || integrity.reason}`, integrity);',
            ),
            "ignore_compute_business_state_tampering": (
                "if (actualStateHash !== expectedStateHash) {",
                "if (false && actualStateHash !== expectedStateHash) {",
            ),
            "post_into_closed_accounting_period": (
                'if (enterprise.ledger.closedPeriods.includes(date.slice(0, 7))) throw new Error(`accounting period is closed: ${date.slice(0, 7)}`);',
                'if (false && enterprise.ledger.closedPeriods.includes(date.slice(0, 7))) throw new Error(`accounting period is closed: ${date.slice(0, 7)}`);',
            ),
            "reuse_idempotency_key_with_different_amount": (
                'if (existingRequest.inputHash !== inputHash) return fail("idempotency_conflict", `journal request key was already used with different input: ${idempotencyKey}`);',
                'if (false && existingRequest.inputHash !== inputHash) return fail("idempotency_conflict", `journal request key was already used with different input: ${idempotencyKey}`);',
            ),
            "append_duplicate_event_on_idempotent_replay": (
                'if (result.ok && !result.replayed && !["compute.verify", "ledger.trial_balance"].includes(type)) recordComputeEvent(enterprise, actor, type, payload, result.item);',
                'if (result.ok && !["compute.verify", "ledger.trial_balance"].includes(type)) recordComputeEvent(enterprise, actor, type, payload, result.item);',
            ),
            "use_receipt_before_available_date": (
                "if (!appliedReceipts.has(receipt.id) && receipt.dueDate <= event.dueDate) {",
                "if (!appliedReceipts.has(receipt.id)) {",
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, (old, new) in mutants.items():
                self.assertEqual(source.count(old), 1, name)
                mutant = root / f"{name}.mjs"
                mutant.write_text(source.replace(old, new), encoding="utf-8")
                completed = subprocess.run(
                    ["node", "--test", str(SUITE)],
                    cwd=ROOT,
                    env={**os.environ, "COMPUTE_MODULE": str(mutant)},
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                self.assertNotEqual(
                    completed.returncode,
                    0,
                    f"surviving critical mutant: {name}\n{completed.stdout}",
                )

    def test_enterprise_contract_suite_kills_governance_mutants(self) -> None:
        source = ENTERPRISE_SOURCE.read_text(encoding="utf-8")
        mutants = {
            "accept_workflow_cycle": (
                'if (!ready.length) throw new Error("workflow job graph contains a cycle");',
                "if (!ready.length) return [];",
            ),
            "allow_self_review": (
                'if (environment.preventSelfReview && run.actor === actor) return fail("self_review_forbidden", "the run initiator cannot approve this deployment");',
                'if (false && environment.preventSelfReview && run.actor === actor) return fail("self_review_forbidden", "the run initiator cannot approve this deployment");',
            ),
            "allow_reviewer_bypass_conflict": (
                'if (bypassActors.some((actor) => requiredReviewers.includes(actor))) throw new Error("a required reviewer cannot also bypass the ruleset");',
                'if (false && bypassActors.some((actor) => requiredReviewers.includes(actor))) throw new Error("a required reviewer cannot also bypass the ruleset");',
            ),
            "ignore_audit_payload_tampering": (
                "if (digest(unsigned) !== hash) return { valid: false, brokenAt: index + 1, reason: \"hash_mismatch\" };",
                "if (false && digest(unsigned) !== hash) return { valid: false, brokenAt: index + 1, reason: \"hash_mismatch\" };",
            ),
            "continue_after_audit_integrity_failure": (
                'if (!integrity.valid) return fail("integrity", "audit chain integrity failed; mutations are blocked", integrity);',
                'if (false && !integrity.valid) return fail("integrity", "audit chain integrity failed; mutations are blocked", integrity);',
            ),
            "append_to_broken_audit_chain": (
                'if (!integrity.valid) throw new Error(`audit chain integrity failed at event ${integrity.brokenAt || "unknown"}`);',
                'if (false && !integrity.valid) throw new Error(`audit chain integrity failed at event ${integrity.brokenAt || "unknown"}`);',
            ),
            "ignore_enterprise_business_state_tampering": (
                "if (actualStateHash !== expectedStateHash) {",
                "if (false && actualStateHash !== expectedStateHash) {",
            ),
            "merge_despite_policy_denial": (
                'if (!evaluation.allowed) return fail("policy_denied", "pull request does not satisfy merge policy", evaluation);',
                'if (false && !evaluation.allowed) return fail("policy_denied", "pull request does not satisfy merge policy", evaluation);',
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, (old, new) in mutants.items():
                self.assertEqual(source.count(old), 1, name)
                mutant = root / f"{name}.mjs"
                mutant.write_text(source.replace(old, new), encoding="utf-8")
                completed = subprocess.run(
                    ["node", "--test", str(ENTERPRISE_SUITE)],
                    cwd=ROOT,
                    env={**os.environ, "ENTERPRISE_MODULE": str(mutant)},
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                self.assertNotEqual(
                    completed.returncode,
                    0,
                    f"surviving governance mutant: {name}\n{completed.stdout}",
                )


if __name__ == "__main__":
    unittest.main()
