import json
import tempfile
import unittest
from pathlib import Path

from factory26_harness.browser_probe import validate_steps
from factory26_harness.trace import ProductionTrace
from factory26_harness.workspace_tools import WorkspaceTools


class ProbePromptContractTests(unittest.TestCase):
    def test_model_facing_example_is_accepted_by_actual_step_validator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = WorkspaceTools(root, ProductionTrace(root / "trace.jsonl"), 33045)
            schema = next(item["function"] for item in tools.schemas()
                          if item["function"]["name"] == "browser_probe")
            description = schema["description"]
            raw = description.split("Example steps: ", 1)[1]
            example, _ = json.JSONDecoder().raw_decode(raw)
            steps = validate_steps(example)
            self.assertEqual([step["action"] for step in steps], ["fill", "click", "reload"])
            self.assertEqual(steps[1]["role"], "button")
            self.assertEqual(steps[1]["name"], "Save")
            self.assertNotIn("label", steps[1])
            self.assertEqual(steps[-1]["expect_text"], ["Saved: Alice"])
            self.assertIn("fresh seed state", description)
            self.assertIn("EXACTLY ONE", description)
