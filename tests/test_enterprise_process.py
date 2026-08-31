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
TEMPLATE = ROOT / "factory26_harness" / "templates" / "github"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def request_json(
    port: int,
    path: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    token: str = "",
) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        method=method,
        headers={
            "content-type": "application/json",
            "x-langqi-world": "process-test",
            **({"authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def authenticate(port: int, username: str) -> str:
    status, payload = request_json(
        port,
        "/api/command",
        method="POST",
        payload={
            "type": "account.authenticate",
            "payload": {
                "login": username,
                "password": "Fixture-password-123!",
            },
        },
    )
    if status != 200 or not payload.get("sessionToken"):
        raise AssertionError(f"authentication failed: {status} {payload}")
    return str(payload["sessionToken"])


class EnterpriseProcessTests(unittest.TestCase):
    def test_server_blocks_merge_and_branch_bypasses_then_persists_valid_merge(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "github"
            shutil.copytree(TEMPLATE, project)
            port = free_port()

            def start(*, reset: bool) -> subprocess.Popen:
                environment = {**os.environ, "PORT": str(port)}
                if reset:
                    environment["FACTORY26_RESET_FIXTURES"] = "1"
                else:
                    environment.pop("FACTORY26_RESET_FIXTURES", None)
                process = subprocess.Popen(
                    ["node", "server.mjs"],
                    cwd=project / "backend",
                    env=environment,
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
                raise AssertionError("GitHub backend did not become ready")

            def stop(process: subprocess.Popen) -> None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
                if process.stdout is not None:
                    process.stdout.close()

            first = start(reset=True)
            try:
                status, anonymous_state = request_json(port, "/api/state")
                self.assertEqual(status, 200)
                self.assertEqual(anonymous_state["accounts"], [])
                status, forged = request_json(
                    port,
                    "/api/command",
                    method="POST",
                    payload={
                        "type": "patch",
                        "payload": {
                            "collection": "repositories",
                            "id": "acme/protection-repo",
                            "patch": {"visibility": "public"},
                        },
                    },
                )
                self.assertEqual(status, 401)
                self.assertEqual(forged["code"], "authentication_required")

                maintainer_token = authenticate(port, "fixture-user-30")
                protection_admin_token = authenticate(port, "fixture-user-24")
                status, authenticated_state = request_json(
                    port, "/api/state", token=protection_admin_token
                )
                self.assertEqual(status, 200)
                self.assertTrue(authenticated_state["accounts"])
                self.assertTrue(
                    all(
                        "password" not in account and "passwordHash" not in account
                        for account in authenticated_state["accounts"]
                    )
                )
                status, undeclared = request_json(
                    port,
                    "/api/command",
                    method="POST",
                    token=protection_admin_token,
                    payload={
                        "type": "patch",
                        "payload": {
                            "collection": "repositories",
                            "id": "acme/protection-repo",
                            "patch": {"owner": "attacker"},
                        },
                    },
                )
                self.assertEqual(status, 422)
                self.assertEqual(undeclared["code"], "validation")

                data_dir = project / "backend" / "data"
                blocked_data_dir = project / "backend" / "data-blocked"
                data_dir.rename(blocked_data_dir)
                data_dir.write_text("persistence path intentionally blocked", encoding="utf-8")
                try:
                    status, failed_write = request_json(
                        port,
                        "/api/command",
                        method="POST",
                        token=protection_admin_token,
                        payload={
                            "type": "patch",
                            "payload": {
                                "collection": "repositories",
                                "id": "acme/protection-repo",
                                "patch": {"visibility": "private"},
                            },
                        },
                    )
                    self.assertEqual(status, 500)
                    self.assertTrue(failed_write["error"])
                finally:
                    data_dir.unlink()
                    blocked_data_dir.rename(data_dir)
                status, after_failed_write = request_json(
                    port, "/api/state", token=protection_admin_token
                )
                self.assertEqual(status, 200)
                protection_repo = next(
                    item
                    for item in after_failed_write["repositories"]
                    if item["id"] == "acme/protection-repo"
                )
                self.assertEqual(protection_repo["visibility"], "public")

                status, bypass = request_json(
                    port,
                    "/api/command",
                    method="POST",
                    payload={
                        "type": "patch",
                        "payload": {
                            "collection": "pullRequests",
                            "id": "acme/pr-repo#8",
                            "patch": {"state": "merged"},
                        },
                    },
                    token=maintainer_token,
                )
                self.assertEqual(status, 409)
                self.assertEqual(bypass["code"], "protected_transition")

                status, _ = request_json(
                    port,
                    "/api/command",
                    method="POST",
                    token=protection_admin_token,
                    payload={
                        "type": "list.add",
                        "payload": {
                            "collection": "repositories",
                            "id": "acme/protection-repo",
                            "field": "protections",
                            "value": {
                                "pattern": "main",
                                "approvals": 1,
                                "statusCheck": "test",
                            },
                            "uniqueKey": "pattern",
                        },
                    },
                )
                self.assertEqual(status, 200)
                status, current = request_json(
                    port, "/api/state", token=protection_admin_token
                )
                self.assertEqual(status, 200)
                protected_repo = next(
                    item
                    for item in current["repositories"]
                    if item["id"] == "acme/protection-repo"
                )
                changed_branches = json.loads(json.dumps(protected_repo["branches"]))
                changed_branches[0]["files"]["bypass.txt"] = "must be rejected"
                status, branch_bypass = request_json(
                    port,
                    "/api/command",
                    method="POST",
                    token=protection_admin_token,
                    payload={
                        "type": "patch",
                        "payload": {
                            "collection": "repositories",
                            "id": protected_repo["id"],
                            "patch": {"branches": changed_branches},
                        },
                    },
                )
                self.assertEqual(status, 409)
                self.assertEqual(branch_bypass["code"], "protected_branch")

                status, merged = request_json(
                    port,
                    "/api/command",
                    method="POST",
                    payload={
                        "type": "pullRequest.merge",
                        "payload": {"id": "acme/pr-repo#8"},
                    },
                    token=maintainer_token,
                )
                self.assertEqual(status, 200)
                self.assertEqual(merged["item"]["state"], "merged")
                status, integrity = request_json(
                    port, "/api/audit/verify", token=maintainer_token
                )
                self.assertEqual(status, 200)
                self.assertTrue(integrity["valid"])
                self.assertTrue(integrity["stateBound"])
            finally:
                stop(first)

            second = start(reset=False)
            try:
                maintainer_token = authenticate(port, "fixture-user-30")
                status, restored = request_json(
                    port, "/api/state", token=maintainer_token
                )
                self.assertEqual(status, 200)
                pull = next(
                    item
                    for item in restored["pullRequests"]
                    if item["id"] == "acme/pr-repo#8"
                )
                self.assertEqual(pull["state"], "merged")
                self.assertTrue(pull["mergeCommit"].startswith("merge-8-"))
            finally:
                stop(second)

            state_path = project / "backend" / "data" / "github-state.json"
            tampered_state = json.loads(state_path.read_text(encoding="utf-8"))
            protection_repo = next(
                item
                for item in tampered_state["repositories"]
                if item["id"] == "acme/protection-repo"
            )
            protection_repo["visibility"] = "private"
            tampered = json.dumps(tampered_state, indent=2).encode()
            state_path.write_bytes(tampered)
            completed = subprocess.run(
                ["node", "server.mjs"],
                cwd=project / "backend",
                env={**os.environ, "PORT": str(free_port())},
                capture_output=True,
                timeout=10,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(state_path.read_bytes(), tampered)
            self.assertIn(b"Refusing to start with invalid GitHub state", completed.stderr)

    def test_corrupt_persisted_state_is_preserved_and_startup_fails_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "github"
            shutil.copytree(TEMPLATE, project)
            data_dir = project / "backend" / "data"
            data_dir.mkdir()
            state_path = data_dir / "github-state.json"
            corrupt = b'{"accounts": [not-json]}'
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
            self.assertIn(b"Refusing to overwrite unreadable GitHub state", completed.stderr)


if __name__ == "__main__":
    unittest.main()
