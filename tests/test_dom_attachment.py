"""Small synthetic DOM attachment regression; no model or browser calls."""
import tempfile
import unittest
from pathlib import Path

from factory26_harness.checks import interaction_policy_check


class DomAttachmentTests(unittest.TestCase):
    def check_source(self, source):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "frontend/src/app.js"
            path.parent.mkdir(parents=True)
            path.write_text(source, encoding="utf-8")
            return interaction_policy_check(root)

    def test_node_after_nested_sibling_argument_is_attached(self):
        for method in ("append", "prepend", "replaceChildren"):
            with self.subTest(method=method):
                result = self.check_source(
                    'const details = document.createElement("p");\n'
                    'details.textContent = "Attached result";\n'
                    f'document.body.{method}(document.createTextNode("Prefix: "), details);\n'
                )
                self.assertTrue(result.passed, result.summary)

    def test_nested_sibling_without_node_remains_detached(self):
        result = self.check_source(
            'const details = document.createElement("p");\n'
            'details.textContent = "Not attached";\n'
            'document.body.append(document.createTextNode("Prefix: "), other);\n'
        )
        self.assertFalse(result.passed)
        self.assertIn("never attaches", result.summary)

    def test_existing_wrapped_node_recognition_is_preserved(self):
        result = self.check_source(
            'function identity(node) { return node; }\n'
            'const details = document.createElement("p");\n'
            'details.textContent = "Attached";\n'
            'document.body.append(identity(details));\n'
        )
        self.assertTrue(result.passed, result.summary)

    def test_unnamed_input_remains_rejected_after_attachment_fix(self):
        result = self.check_source(
            'const input = document.createElement("input");\n'
            'input.value = "fixture";\n'
            'document.body.append(document.createTextNode("Prefix: "), input);\n'
        )
        self.assertFalse(result.passed)
        self.assertIn("without aria-label", result.summary)
        self.assertNotIn("never attaches", result.summary)

    def test_exact_manual_browser_fixture_passes_static_check(self):
        root = Path(__file__).resolve().parents[1] / "docs/diagnostics/dom-attachment-fixture"
        result = interaction_policy_check(root)
        self.assertTrue(result.passed, result.summary)


if __name__ == "__main__":
    unittest.main()
