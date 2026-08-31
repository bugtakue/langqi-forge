from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GitHubAuthenticationTests(unittest.TestCase):
    def test_node_authentication_and_authorization_contract(self) -> None:
        environment = {
            **os.environ,
            "GITHUB_AUTH_MODULE": str(
                ROOT
                / "factory26_harness"
                / "templates"
                / "github"
                / "backend"
                / "auth.mjs"
            ),
            "GITHUB_AUTHORIZATION_MODULE": str(
                ROOT
                / "factory26_harness"
                / "templates"
                / "github"
                / "backend"
                / "authorization.mjs"
            ),
        }
        completed = subprocess.run(
            ["node", "--test", str(ROOT / "tests" / "github_auth.test.mjs")],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
