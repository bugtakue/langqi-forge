"""Submission-entry policy tests; no model, browser or application execution."""
import os
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

from factory26_harness import qualifier
from factory26_harness.agent import _completion_tail_enabled


class EntryCompletionPolicyTests(unittest.TestCase):
    def run_entry(self, environment):
        entry = Path(qualifier.__file__).resolve().parent.parent / "main.py"
        observed = []

        def check_policy():
            observed.append(_completion_tail_enabled())
            return 0

        with patch.dict(os.environ, environment, clear=True), \
             patch.object(qualifier, "main", side_effect=check_policy) as runner:
            with self.assertRaises(SystemExit) as raised:
                runpy.run_path(str(entry), run_name="__main__")
            self.assertEqual(raised.exception.code, 0)
            runner.assert_called_once_with()
        return observed

    def test_entry_opts_in_without_changing_library_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(_completion_tail_enabled())
        self.assertEqual(self.run_entry({}), [True])

    def test_explicit_disable_is_respected(self):
        self.assertEqual(self.run_entry({"FACTORY26_COMPLETION_TAIL": "0"}), [False])

    def test_explicit_enable_is_respected(self):
        self.assertEqual(self.run_entry({"FACTORY26_COMPLETION_TAIL": "1"}), [True])

    def test_invalid_runner_override_is_not_silently_replaced(self):
        with self.assertRaisesRegex(ValueError, "must be 0 or 1"):
            self.run_entry({"FACTORY26_COMPLETION_TAIL": "invalid"})
