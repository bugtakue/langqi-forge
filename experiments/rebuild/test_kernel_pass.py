import json
from pathlib import Path
import tempfile
import unittest

from kernel_pass import build_prompt, graph, seed, upstream


class KernelPassTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
