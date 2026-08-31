from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class DryRunIntegrationTests(unittest.TestCase):
    def test_contract_build_start_health_and_trace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            requirements = temporary / "requirements"
            output = temporary / "output"
            requirements.mkdir()
            (requirements / "requirements.yaml").write_text(
                """id: app
name: Demo application
type: FOLDER
children:
  - id: item-create
    name: Create an item
    type: ATOMIC
    description: A user can enter a name and save an item.
    scenarios:
      - id: create-success
        name: Save a valid item
        steps:
          - keyword: Given
            content: the application is open
          - keyword: When
            content: the user enters a name and selects Save
          - keyword: Then
            content: the item remains after refresh
""",
                encoding="utf-8",
            )
            command = [
                sys.executable,
                str(REPOSITORY_ROOT / "main.py"),
                str(requirements),
                "--output-dir",
                str(output),
                "--web-port",
                "3988",
                "--smoke-port",
                "3989",
                "--dry-run",
                "--strict-exit",
            ]
            completed = subprocess.run(
                command,
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + "\n" + completed.stderr)
            self.assertTrue((output / "frontend" / "dist" / "index.html").is_file())
            self.assertTrue((output / "backend" / "server.mjs").is_file())
            report = json.loads((output / ".arc" / "harness-report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["all_local_checks_passed"])
            self.assertEqual(report["requirement_count"], 1)
            events = (output / ".arc" / "runner-events.jsonl").read_text(encoding="utf-8")
            self.assertIn('"state": "completed"', events)
            self.assertTrue((output / ".arc" / "traceability" / "requirements.json").is_file())
            contract_tests = json.loads(
                (output / ".arc" / "traceability" / "tests.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(contract_tests), 1)
            self.assertIsNone(next(iter(contract_tests.values()))["passed"])
            log = subprocess.run(
                ["git", "log", "--oneline"], cwd=output, capture_output=True, text=True, check=True
            ).stdout.splitlines()
            self.assertGreaterEqual(len(log), 2)

    def test_sheet_domain_uses_full_template(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            requirements = temporary / "requirements"
            output = temporary / "output"
            requirements.mkdir()
            (requirements / "requirements.yaml").write_text(
                """id: sheet-app
name: Online Spreadsheet Data Workspace
type: FOLDER
children:
  - id: edit-cell
    name: Edit a spreadsheet cell
    type: ATOMIC
    description: A user can edit a cell and keep the value after refresh.
""",
                encoding="utf-8",
            )
            command = [
                sys.executable,
                str(REPOSITORY_ROOT / "main.py"),
                str(requirements),
                "--output-dir",
                str(output),
                "--web-port",
                "3990",
                "--smoke-port",
                "3991",
                "--dry-run",
                "--strict-exit",
            ]
            completed = subprocess.run(
                command,
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + "\n" + completed.stderr)
            frontend = (output / "frontend" / "src" / "app.js").read_text(encoding="utf-8")
            backend = (output / "backend" / "server.mjs").read_text(encoding="utf-8")
            self.assertIn("Pivot table editor", frontend)
            self.assertIn("/api/workbooks", backend)
            plan = json.loads((output / ".arc" / "compiled-plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["detected_domain"], "sheet")
            report = json.loads((output / ".arc" / "harness-report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["all_local_checks_passed"])


if __name__ == "__main__":
    unittest.main()
