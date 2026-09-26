import json
from pathlib import Path
from unittest.mock import patch
import tempfile
import time
import unittest

from kernel_pass import build_prompt, dispatch_pipeline, frozen_test_text, graph, seed, upstream
from grade import manifest
import kernel_pass


class KernelPassTests(unittest.TestCase):
    def test_actual_cli_accepts_recovery_360_second_bound_before_model_launch(self):
        with patch('sys.argv', ['kernel_pass.py', '--output', '/unit-output', '--seconds', '360']), \
             patch.object(kernel_pass, 'run', return_value=0) as launch:
            self.assertEqual(kernel_pass.main(), 0)
            launch.assert_called_once_with(Path('/unit-output'), 360)

    def test_dispatch_wait_matches_bounded_upstream_request_not_90_seconds(self):
        class Failed:
            def run_turn(self, text, timeout):
                self.timeout = timeout
                return False, 'transport error'
        session = Failed()
        with self.assertRaisesRegex(RuntimeError, 'no transport/error retry'):
            dispatch_pipeline(session, time.monotonic()+600, lambda:False, lambda:False, lambda *args:None)
        self.assertEqual(session.timeout, 240)

    def test_dispatch_never_repeats_observed_tool_or_failed_request(self):
        class Fake:
            def __init__(self, result):
                self.calls, self.result = 0, result
            def run_turn(self, text, timeout):
                self.calls += 1
                return self.result
        for has_tool in (True, False):
            session = Fake((True, 'ok'))
            if has_tool:
                dispatch_pipeline(session, time.monotonic()+60, lambda:False, lambda:True, lambda *args:None)
                self.assertEqual(session.calls, 1)
            else:
                with self.assertRaisesRegex(RuntimeError, 'nothing launched'):
                    dispatch_pipeline(session, time.monotonic()+60, lambda:False, lambda:False, lambda *args:None)
                self.assertEqual(session.calls, 2)
        session = Fake((False, 'transport error'))
        with self.assertRaisesRegex(RuntimeError, 'no transport/error retry'):
            dispatch_pipeline(session, time.monotonic()+60, lambda:False, lambda:False, lambda *args:None)
        self.assertEqual(session.calls, 1)

    def test_graph_has_one_bounded_coder_no_self_grading_or_repair_loop(self):
        module = upstream()
        dot = graph(module, 'runtime data {page} "quote"', 360)
        self.assertEqual(dot.count('handler="codergen"'), 1)
        self.assertEqual(dot.count('handler="shell_check"'), 1)
        self.assertIn('max_iterations="20"', dot)
        self.assertIn('max_retries="0"', dot)
        self.assertIn('--seed /source', dot)
        self.assertNotIn('verify_node.py', dot)
        self.assertNotIn('shell,', dot)
        self.assertIn('{{page}}', dot)

    def test_failed_work_is_copied_not_replaced_with_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for part in ('frontend', 'backend'):
                (root / 'source' / part).mkdir(parents=True)
                (root / 'source' / part / 'partial.txt').write_text('retained failing work')
            (root / 'destination').mkdir()
            seed(root / 'source', root / 'destination')
            self.assertEqual((root / 'destination/backend/partial.txt').read_text(), 'retained failing work')
            with self.assertRaises(FileExistsError):
                seed(root / 'source', root / 'destination')

    def test_runtime_prompt_preserves_inputs_but_has_no_task_answer(self):
        catalog = {'nodes': [{'id': 'arbitrary-id'}], 'contracts': {'root': 'runtime-only-sentinel'}}
        prompt = build_prompt(catalog, 'frozen-test-sentinel', 'actual-failure-sentinel')
        self.assertIn('runtime-only-sentinel', prompt)
        self.assertIn('frozen-test-sentinel', prompt)
        self.assertIn('actual-failure-sentinel', prompt)
        self.assertNotIn('foundation/identity.spec.ts', prompt)

    def test_only_explicit_frozen_specs_are_read_and_changes_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'suite').mkdir()
            (root / 'suite/named.spec.ts').write_text('// behavior sentinel')
            (root / 'suite/restart.ts').write_text('// controller helper')
            (root / 'private.spec.ts').write_text('// forbidden discovery sentinel')
            frozen = {'tests_sha256': manifest(root / 'suite')}
            value = frozen_test_text(root, frozen)
            self.assertIn('behavior sentinel', value)
            self.assertNotIn('forbidden discovery', value)
            self.assertNotIn('controller helper', value)
            (root / 'suite/named.spec.ts').write_text('// edited')
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                frozen_test_text(root, frozen)


if __name__ == '__main__':
    unittest.main()
