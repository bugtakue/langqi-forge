from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "factory26_harness" / "templates" / "sheet"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def request_json(
    port: int, path: str, *, method: str = "GET", payload: dict | None = None
) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        method=method,
        headers={"content-type": "application/json", "x-langqi-user": "process-test"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


class ComputeProcessTests(unittest.TestCase):
    def test_corrupt_persisted_state_is_preserved_and_startup_fails_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "sheet"
            shutil.copytree(TEMPLATE, project)
            data_dir = project / "backend" / "data"
            data_dir.mkdir()
            state_path = data_dir / "sheet-state.json"
            corrupt = b'{"workbooks": [not-json]}'
            state_path.write_bytes(corrupt)
            completed = subprocess.run(
                ["node", "server.mjs"],
                cwd=project / "backend",
                env={**os.environ, "PORT": str(free_port())},
                capture_output=True,
                timeout=10,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(state_path.read_bytes(), corrupt)
            self.assertIn(b"Refusing to overwrite unreadable spreadsheet state", completed.stderr)

    def test_enterprise_state_survives_process_restart_and_oversize_fails_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "sheet"
            shutil.copytree(TEMPLATE, project)
            subprocess.run(
                ["node", "build.mjs"],
                cwd=project / "frontend",
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            port = free_port()

            def start() -> subprocess.Popen:
                process = subprocess.Popen(
                    ["node", "server.mjs"],
                    cwd=project / "backend",
                    env={**os.environ, "PORT": str(port)},
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    start_new_session=True,
                )
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    try:
                        status, body = request_json(port, "/api/health")
                        if status == 200 and body.get("ready") is True:
                            return process
                    except (OSError, ValueError):
                        pass
                    time.sleep(0.05)
                process.kill()
                raise AssertionError("sheet backend did not become ready")

            def stop(process: subprocess.Popen) -> None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
                if process.stdout is not None:
                    process.stdout.close()

            first = start()
            try:
                status, workbook = request_json(
                    port,
                    "/api/workbooks",
                    method="POST",
                    payload={"name": "Restart contract"},
                )
                self.assertEqual(status, 201)
                workbook_id = workbook["id"]
                status, posted = request_json(
                    port,
                    f"/api/workbooks/{workbook_id}/compute",
                    method="POST",
                    payload={
                        "type": "ledger.account.upsert",
                        "payload": {
                            "code": "1000",
                            "name": "Cash",
                            "accountType": "asset",
                        },
                        "expectedRevision": 0,
                    },
                )
                self.assertEqual(status, 200)
                self.assertEqual(posted["enterprise"]["revision"], 1)
                self.assertTrue(posted["integrity"]["valid"])

                status, missing_precondition = request_json(
                    port,
                    f"/api/workbooks/{workbook_id}/compute",
                    method="POST",
                    payload={
                        "type": "ledger.account.upsert",
                        "payload": {
                            "code": "2000",
                            "name": "Payables",
                            "accountType": "liability",
                        },
                    },
                )
                self.assertEqual(status, 428)
                self.assertEqual(missing_precondition["code"], "revision_required")

                status, second_account = request_json(
                    port,
                    f"/api/workbooks/{workbook_id}/compute",
                    method="POST",
                    payload={
                        "type": "ledger.account.upsert",
                        "payload": {
                            "code": "3000",
                            "name": "Opening equity",
                            "accountType": "equity",
                        },
                        "expectedRevision": 1,
                    },
                )
                self.assertEqual(status, 200)
                self.assertEqual(second_account["enterprise"]["revision"], 2)
                journal_command = {
                    "type": "ledger.journal.post",
                    "payload": {
                        "date": "2026-09-01",
                        "reference": "PROCESS-OPEN-1",
                        "lines": [
                            {"accountCode": "1000", "debit": 50},
                            {"accountCode": "3000", "credit": 50},
                        ],
                    },
                    "expectedRevision": 2,
                }
                status, first_journal = request_json(
                    port,
                    f"/api/workbooks/{workbook_id}/compute",
                    method="POST",
                    payload=journal_command,
                )
                self.assertEqual(status, 200)
                self.assertEqual(first_journal["enterprise"]["revision"], 3)
                journal_id = first_journal["item"]["id"]
                replay_command = {**journal_command, "expectedRevision": 3}
                status, replay = request_json(
                    port,
                    f"/api/workbooks/{workbook_id}/compute",
                    method="POST",
                    payload=replay_command,
                )
                self.assertEqual(status, 200)
                self.assertTrue(replay["replayed"])
                self.assertEqual(replay["item"]["id"], journal_id)
                self.assertEqual(replay["enterprise"]["revision"], 3)
                self.assertEqual(len(replay["enterprise"]["ledger"]["journals"]), 1)
            finally:
                stop(first)

            second = start()
            try:
                status, restored = request_json(
                    port, f"/api/workbooks/{workbook_id}/compute"
                )
                self.assertEqual(status, 200)
                self.assertEqual(restored["enterprise"]["revision"], 3)
                self.assertTrue(restored["integrity"]["valid"])
                self.assertEqual(
                    restored["enterprise"]["ledger"]["accounts"][0]["code"],
                    "1000",
                )

                oversized = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/workbooks/{workbook_id}/compute",
                    data=(b'x' * 1_048_577),
                    method="POST",
                    headers={"content-type": "application/json"},
                )
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(oversized, timeout=10)
                self.assertEqual(raised.exception.code, 413)
                status, unchanged = request_json(
                    port, f"/api/workbooks/{workbook_id}/compute"
                )
                self.assertEqual(status, 200)
                self.assertEqual(unchanged["enterprise"]["revision"], 3)
            finally:
                stop(second)


if __name__ == "__main__":
    unittest.main()
