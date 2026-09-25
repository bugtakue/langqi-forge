"""Protocol feedback fixtures, not live-browser or official quality evidence."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory26_harness.browser_probe import ALLOWED_ACTIONS, MAX_ASSERTIONS, MAX_STEPS
from factory26_harness.trace import ProductionTrace, verify_trace_rows
from factory26_harness.workspace_tools import WorkspaceTools


class ProbePlanDiagnosticsTests(unittest.TestCase):
    def test_one_rejection_reports_multiple_invalid_steps_without_launch_or_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = ProductionTrace(root / 'trace.jsonl')
            tools = WorkspaceTools(root, trace, 33143)
            tools.last_validation_passed = True
            tools.validated_revision = 0
            tools.validation_scope = 'quick'
            steps = [
                {'action': 'reload', 'expect_text': ['Ready']},
                {'action': 'assert', 'expect_text': ['Ready']},
                {'action': 'reload', 'expect_text': ['x'] * (MAX_ASSERTIONS + 1)},
                {'action': 'navigate', 'path': 'https://example.invalid'},
            ]
            before = copy.deepcopy(steps)
            with patch('factory26_harness.workspace_tools.probe_local_app') as probe:
                result = json.loads(tools.execute('browser_probe', {'steps': steps}))
                self.assertFalse(result['ok'])
                self.assertIn('unsupported action', result['error'])
                diagnostic = result['plan_diagnostics']
                self.assertEqual(diagnostic['supplied_steps'], 4)
                self.assertEqual(diagnostic['maximum_steps'], MAX_STEPS)
                self.assertEqual(diagnostic['maximum_assertions_per_field'], MAX_ASSERTIONS)
                self.assertEqual(diagnostic['allowed_actions'], sorted(ALLOWED_ACTIONS))
                self.assertEqual([e['step'] for e in diagnostic['step_errors']], [2, 3, 4])
                self.assertIn('browser step 2', diagnostic['step_errors'][0]['error'])
                self.assertEqual(diagnostic['steps_inspected'], 4)
                self.assertFalse(diagnostic['plan_executed'])
                probe.assert_not_called()
            self.assertEqual(steps, before)
            self.assertEqual(tools.browser_probe_calls, 0)
            self.assertTrue(tools.browser_probe_requires_recheck)
            self.assertEqual(tools.browser_probe_verified_revision, -1)
            self.assertEqual(tools.verified_browser_flows, [])
            rows = [json.loads(line) for line in trace.path.read_text().splitlines()]
            self.assertTrue(verify_trace_rows(rows, require_fully_sealed=True)['valid'])
            self.assertEqual(rows[-1]['payload']['result']['plan_diagnostics'], diagnostic)

    def test_type_length_and_step_errors_are_distinct_and_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            tools = WorkspaceTools(Path(directory), ProductionTrace(Path(directory) / 'trace.jsonl'), 33143)
            tools.last_validation_passed = True
            tools.validated_revision = 0
            tools.validation_scope = 'quick'
            for value, count, errors in ((None, None, 0), ('private input', None, 0),
                                         ([{'action': 'reload'}] * 17, 17, 0),
                                         ([{'action': 'unsupported'}] * 1000, 1000, 8)):
                with self.subTest(count=count), patch('factory26_harness.workspace_tools.probe_local_app') as probe:
                    encoded = tools.execute('browser_probe', {'steps': value})
                    result = json.loads(encoded)
                    self.assertFalse(result['ok'])
                    diagnostic = result['plan_diagnostics']
                    self.assertEqual(diagnostic['supplied_steps'], count)
                    self.assertEqual(len(diagnostic['step_errors']), errors)
                    self.assertLessEqual(diagnostic['steps_inspected'], MAX_STEPS)
                    self.assertLess(len(encoded), 4000)
                    self.assertNotIn('private input', encoded)
                    probe.assert_not_called()
                    self.assertEqual(tools.browser_probe_calls, 0)

    def test_correction_still_needs_real_probe_and_uses_original_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            tools = WorkspaceTools(Path(directory), ProductionTrace(Path(directory) / 'trace.jsonl'), 33143)
            tools.last_validation_passed = True
            tools.validated_revision = 0
            tools.validation_scope = 'quick'
            invalid = [{'action': 'click', 'role': 'button', 'name': 'Save',
                        'expect_text': ['Saved'] * (MAX_ASSERTIONS + 1)}]
            valid = [{'action': 'click', 'role': 'button', 'name': 'Save', 'expect_text': ['Saved']}]
            with patch('factory26_harness.workspace_tools.probe_local_app') as probe:
                rejected = json.loads(tools.execute('browser_probe', {'steps': invalid}))
                self.assertIn('plan_diagnostics', rejected)
                probe.assert_not_called()
                probe.return_value = {'ok': True, 'behavioral_checks': 1, 'behavioral_assertions': 1}
                accepted = json.loads(tools.execute('browser_probe', {'steps': valid}))
                self.assertTrue(accepted['ok'])
                self.assertNotIn('plan_diagnostics', accepted)
                self.assertEqual(tools.browser_probe_calls, 1)
                self.assertFalse(tools.browser_probe_requires_recheck)
                self.assertEqual(tools.browser_probe_verified_revision, 0)
                self.assertEqual(len(tools.verified_browser_flows), 1)
                tools.browser_probe_calls = tools.maximum_browser_probe_calls
                exhausted = json.loads(tools.execute('browser_probe', {'steps': invalid}))
                self.assertIn('budget exhausted', exhausted['error'])
                self.assertNotIn('plan_diagnostics', exhausted)
                self.assertEqual(probe.call_count, 1)


if __name__ == '__main__':
    unittest.main()
