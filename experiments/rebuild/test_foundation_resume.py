"""Synthetic controller tests: never model calls or application score evidence."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from checkpoints import Checkpoints, application_manifest, case_outcomes
from grade import manifest
import foundation_resume as resume
from run_foundation_trial import continue_working


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'unit-foundation'
        self.compiler = self.base / 'unit-compiler'
        self.suite = self.compiler / 'result/acceptance/suite'
        self.suite.mkdir(parents=True)
        (self.suite / 'unit.spec.ts').write_text('// unit fixture, not a behavior test')
        self.tests = manifest(self.suite)
        write_json(self.compiler / 'manifest.json', {'image': 'unit-image'})
        write_json(self.compiler / 'result/acceptance/frozen.json', {
            'tests_sha256': self.tests, 'requirements_sha256': 'unit-public-source', 'expected': 1})
        write_json(self.compiler / 'result/blank-control/verdict.json', {'gate': True})
        bundle = self.root / 'bundle'
        bundle.mkdir(parents=True)
        (bundle / 'unit.py').write_text('# frozen unit fixture')
        self.work = self.root / 'attempt-1/pass/working'
        for part in ('frontend', 'backend'):
            (self.work / part).mkdir(parents=True)
            (self.work / part / 'partial.txt').write_text('failing original bytes')
        self.report = {'suites': [{'specs': [{'file': 'unit.spec.ts', 'line': 1, 'title': 'unit failure',
            'tests': [{'expectedStatus': 'passed', 'status': 'unexpected', 'results': [
                {'status': 'failed', 'retry': 0, 'errors': [{'message': 'actual runtime failure'}]}]}]}]}],
            'stats': {'startTime': '1970-01-01T00:18:20Z', 'duration': 1000}}
        evidence = self.root / 'attempt-1/runtime-evidence'
        self.proof = self.evidence(evidence, self.report)
        self.store = Checkpoints(self.root / 'checkpoints', self.tests, list(case_outcomes(self.report)))
        decision = self.store.record('foundation', self.work, evidence, self.proof)
        self.metadata = {'name': self.root.name, 'model': 'glm-5.3-flash', 'phase': 'mechanism',
            'cap_cny': 3, 'started': 1000, 'finished': 1200, 'deadline_seconds': 1800, 'max_passes': 3,
            'passes': [{'attempt': 1, 'decision': decision}], 'bundle_sha256': manifest(bundle),
            'compiler_trial': str(self.compiler), 'runtime_tests': self.tests,
            'source_sha256': 'unit-public-source'}
        write_json(self.root / 'manifest.json', self.metadata)
        self.status = {'unresolved_cost_lock': True,
            'trials': [{'id': self.root.name, 'cap': 3000000, 'closed': True}],
            'calls': [{'id': 'unit-settled', 'trial': self.root.name, 'charged': 116508},
                      {'id': 'unit-unknown', 'trial': self.root.name, 'charged': 226807}]}

    def evidence(self, directory, report):
        write_json(directory / 'playwright.json', report)
        write_json(directory / 'verdict.json', {'source_manifest': application_manifest(self.work),
            'test_manifest': self.tests, 'source_unchanged': True, 'tests_unchanged': True,
            'process_cleaned': True, 'passed': 0, 'total': 1, 'gate': False, 'test_exit': 1,
            'evidence_kind': 'synthetic-unit-fixture-not-application-score'})
        proof = manifest(directory)
        (directory / 'raw-controller.log').write_text(json.dumps({'export_manifest': proof}))
        return proof

    def test_plan_carries_cost_time_passes_and_does_not_mutate(self):
        before = manifest(self.base)
        plan = resume.build_plan(self.root, self.status)
        self.assertEqual(plan['remaining_cap_micro_cny'], 2656685)
        self.assertEqual(plan['prior_charged_micro_cny'], 343315)
        self.assertEqual(plan['remaining_seconds'], 1600)
        self.assertEqual(plan['remaining_passes'], 2)
        self.assertEqual(plan['stagnant_rounds'], 1)
        self.assertFalse(plan['execution_allowed'])
        self.assertFalse(plan['official_upload_allowed'])
        self.assertEqual(manifest(self.base), before)

    def test_post_close_evidence_cannot_be_omitted_to_reset_clock(self):
        report = deepcopy(self.report)
        report['stats'] = {'startTime': datetime.fromtimestamp(1300, timezone.utc).isoformat(), 'duration': 100000}
        directory = self.root / 'holdout-after-billing-stop'
        self.evidence(directory, report)
        plan = resume.build_plan(self.root, self.status)
        explicit = resume.build_plan(self.root, self.status, [directory, directory])
        self.assertEqual(plan, explicit)
        self.assertEqual(plan['remaining_seconds'], 1400)
        self.assertEqual(len(plan['post_close_evidence']), 1)
        with self.assertRaisesRegex(ValueError, 'belong'):
            resume.build_plan(self.root, self.status, [self.base])

    def test_restore_keeps_exact_failed_source_and_runtime_only_feedback(self):
        plan = resume.build_plan(self.root, self.status)
        before = manifest(self.root)
        copy = self.base / 'restore-proof'
        with patch.object(resume, 'control', side_effect=AssertionError('no gateway writes allowed')):
            work = resume.restore(plan, copy)
        self.assertEqual(application_manifest(work), plan['source_manifest'])
        self.assertIn('actual runtime failure', (copy / 'feedback.txt').read_text())
        self.assertFalse((copy / 'working/frontend/src/app.js').exists())
        self.assertEqual(manifest(self.root), before)
        with self.assertRaises(FileExistsError):
            resume.restore(plan, copy)

    def test_new_bounded_repair_inherits_source_tests_and_no_gain_history(self):
        # A new explicitly bounded mechanism tranche, not a silent retry or a
        # fresh template. No actual model call occurs in this fixture.
        plan = resume.build_plan(self.root, self.status)
        previous = self.root / 'completed-repair'
        previous.mkdir()
        import shutil
        shutil.copytree(self.root / 'attempt-1', previous / 'attempt-1')
        write_json(previous / 'resume-plan.json', plan)
        decision = self.store.history()[-1]
        write_json(previous / 'result.json', {'resume_trial': self.root.name, 'foundation_gate': False,
            'passes': [{'attempt': 1, 'passed': 0, 'total': 1, 'decision': decision}]})
        out = self.base / 'next-tranche'
        out.mkdir()
        frozen = json.loads((self.compiler / 'result/acceptance/frozen.json').read_text())
        lineage = continue_working(previous, out, frozen, self.status)
        self.assertEqual(lineage['stagnant_rounds'], 1)
        self.assertEqual(application_manifest(out / 'initial-working'), application_manifest(self.work))
        copied = Checkpoints(out / 'checkpoints', self.tests, list(case_outcomes(self.report)))
        self.assertEqual(copied.history(), self.store.history())
        self.assertEqual(manifest(out / 'bundle'), manifest(self.root / 'bundle'))

    def test_bundle_test_source_and_checkpoint_drift_are_rejected(self):
        targets = [self.root / 'bundle/unit.py', self.suite / 'unit.spec.ts',
            self.work / 'frontend/partial.txt',
            self.root / 'checkpoints/snapshots' / self.metadata['passes'][0]['decision']['snapshot'] / 'backend/partial.txt']
        for path in targets:
            with self.subTest(path=path):
                old = path.read_bytes()
                try:
                    path.write_text('tampered')
                    with self.assertRaises(ValueError):
                        resume.build_plan(self.root, self.status)
                finally:
                    path.write_bytes(old)

    def test_unknown_cost_blocks_execute_before_any_docker_or_trial(self):
        plan = resume.build_plan(self.root, self.status)
        with patch.object(resume, 'control', return_value=self.status) as gateway, \
             patch.object(resume.subprocess, 'check_output') as docker, \
             patch.object(resume, 'coding_pass') as model:
            with self.assertRaisesRegex(ValueError, 'gate is closed'):
                resume.execute(plan, [])
        gateway.assert_called_once_with('/status', {'read': True})
        docker.assert_not_called()
        model.assert_not_called()
        self.assertFalse((self.root / 'continuation-1').exists())

    def test_other_open_trial_prevents_continuation(self):
        self.status['unresolved_cost_lock'] = False
        self.status['trials'].append({'id': 'other-trial', 'closed': False})
        plan = resume.build_plan(self.root, self.status)
        self.assertFalse(plan['execution_allowed'])
        self.assertIn('another live trial exists', plan['blockers'])

    def test_duplicate_resume_even_closed_is_rejected(self):
        self.status['trials'].append({'id': self.root.name + '-resume-1', 'closed': True})
        with self.assertRaisesRegex(ValueError, 'continuation already exists'):
            resume.build_plan(self.root, self.status)

    def test_existing_continuation_artifacts_are_not_overwritten(self):
        (self.root / 'continuation-1').mkdir()
        with self.assertRaisesRegex(ValueError, 'artifacts already exist'):
            resume.build_plan(self.root, self.status)

    def test_exhausted_allowances_are_not_renewed(self):
        for field, value in (('max_passes', 1), ('deadline_seconds', 999)):
            with self.subTest(field=field):
                changed = dict(self.metadata, **{field: value})
                write_json(self.root / 'manifest.json', changed)
                with self.assertRaisesRegex(ValueError, 'allowance exhausted'):
                    resume.build_plan(self.root, self.status)
        write_json(self.root / 'manifest.json', self.metadata)
        self.status['calls'][0]['charged'] = 3000000
        with self.assertRaisesRegex(ValueError, 'allowance exhausted'):
            resume.build_plan(self.root, self.status)

    def test_second_no_gain_is_still_paused_not_reset_by_resume(self):
        report = deepcopy(self.report)
        report['stats']['duration'] = 2000
        evidence = self.root / 'attempt-2/runtime-evidence'
        proof = self.evidence(evidence, report)
        decision = self.store.record('foundation', self.work, evidence, proof)
        self.assertEqual(decision['stagnant_rounds'], 2)
        self.assertTrue(decision['pause_module'])
        self.metadata['passes'].append({'attempt': 2, 'decision': decision})
        write_json(self.root / 'manifest.json', self.metadata)
        with self.assertRaisesRegex(ValueError, 'paused'):
            resume.build_plan(self.root, self.status)

    def test_lifecycle_uses_remainder_and_holds_serial_lock_through_validation(self):
        self.status['unresolved_cost_lock'] = False
        plan = resume.build_plan(self.root, self.status)
        events = []
        def gateway(path, payload):
            events.append((path, payload))
            return {'token': 'unit-only'} if path == '/trial' else self.status
        def independent(*args):
            self.assertFalse(any(path == '/close' for path, _ in events))
            events.append(('independent-validation', {}))
        with patch.object(resume, 'execution_gate'), patch.object(resume, 'control', side_effect=gateway), \
             patch.object(resume, 'repair_loop', return_value=None), \
             patch.object(resume, 'independent_delivery', side_effect=independent):
            self.assertEqual(resume.execute(plan, []), 1)
        self.assertEqual(events[0][1]['cap_cny'], 2.656685)
        self.assertEqual(events[0][1]['seconds'], 1600)
        self.assertEqual([path for path, _ in events], ['/trial', 'independent-validation', '/close', '/status'])
        result = json.loads((self.root / 'continuation-1/result.json').read_text())
        self.assertEqual(result['cumulative_cost_upper_cny'], 0.343315)
        self.assertFalse(result['foundation_gate'])

    def test_money_rejects_nonfinite_negative_and_submicro_amounts(self):
        self.assertEqual(resume.money('0.226807'), 226807)
        for value in ('NaN', 'Infinity', '-1', '0.0000001'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                resume.money(value)


if __name__ == '__main__':
    unittest.main()
