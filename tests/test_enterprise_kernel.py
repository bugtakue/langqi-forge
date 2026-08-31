from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


class EnterpriseKernelTests(unittest.TestCase):
    def test_node_enterprise_contract_suite(self) -> None:
        root = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            ["node", "--test", str(root / "tests" / "enterprise_kernel.test.mjs")],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            completed.stdout + "\n" + completed.stderr,
        )


if __name__ == "__main__":
    unittest.main()
