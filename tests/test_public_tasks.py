from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from factory26_harness.public_tasks import sync_public_task


class _TaskApiHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if "/tests" in self.path:
            payload = {
                "files": [
                    {"path": "REQ-1.spec.ts", "content": "import { test } from '@playwright/test';\ntest('one', async () => {});\n"}
                ],
                "public_downloads": None,
            }
        else:
            payload = {
                "id": "demo",
                "title": "Demo",
                "module_count": 1,
                "total_tests": 1,
                "requirements_yaml": "id: ROOT\ntype: FOLDER\nchildren:\n  - id: REQ-1\n    type: ATOMIC\n",
                "requirements_markdown": "# Demo\n",
                "prerequisites_markdown": "",
            }
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class PublicTaskSyncTests(unittest.TestCase):
    def test_syncs_and_hashes_a_public_task(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _TaskApiHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                manifest = sync_public_task(
                    "demo", root, base_url=f"http://127.0.0.1:{server.server_port}"
                )
                self.assertEqual(manifest["observed_test_count"], 1)
                self.assertTrue((root / "demo" / "requirements" / "requirements.yaml").is_file())
                self.assertTrue((root / "demo" / "tests" / "REQ-1.spec.ts").is_file())
        finally:
            server.shutdown()
            server.server_close()

    def test_rejects_unsafe_task_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                sync_public_task("../escape", Path(directory), base_url="http://127.0.0.1:1")


if __name__ == "__main__":
    unittest.main()
