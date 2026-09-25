"""Independent API checks on our disposable Pro identity artifact only.

Requires the reviewed local Node process on 127.0.0.1:19437. This is not an
official GUI test, hidden test, submitted runtime module or model call.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request


root = Path(sys.argv[1]).resolve()
if not any(p.name.startswith("factory26-pro-identity.") for p in root.parents):
    raise SystemExit("Supply template/ in a disposable factory26-pro-identity.* copy")
state_path = root / "backend/data/state.json"
base = "http://127.0.0.1:19437"


def request(path, data=None):
    req = urllib.request.Request(
        base + path, data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def state_hash():
    return hashlib.sha256(state_path.read_bytes()).hexdigest()


checks = []


def check(name, passed):
    checks.append({"check": name, "passed": bool(passed)})
    if not passed:
        raise AssertionError(name)


rows = []
try:
    check("local health", request("/api/health")[0] == 200)
    before = state_hash()
    status, body = request("/api/register", {
        "username": "-invalid-review", "email": "not-an-email", "password": "short",
        "confirm": "different", "terms": False,
    })
    check("invalid registration returns four required field errors", status == 400
          and {"username", "email", "password", "terms"} <= set(body.get("fieldErrors", {})))
    check("rejected registration preserves state exactly", state_hash() == before)
    tag = str(time.time_ns())[-12:]
    for group in range(3):
        username = f"pro-race-{tag}-{group}"
        registration = {
            "username": username, "email": username + "@example.test",
            "password": "Local-race-test-123!", "confirm": "Local-race-test-123!", "terms": True,
        }
        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(lambda _: request("/api/register", registration)[0], range(8)))
        state = json.loads(state_path.read_text())
        stored = sum(account["username"] == username for account in state["accounts"])
        rows.append({"group": group + 1, "statuses": sorted(statuses), "stored_accounts": stored})
        check(f"race group {group + 1}: one commit and seven rejections",
              sorted(statuses) == [200] + [400] * 7 and stored == 1)
        before = state_hash()
        check(f"race group {group + 1}: sequential duplicate rejects without mutation",
              request("/api/register", registration)[0] == 400 and state_hash() == before)
    before = state_hash()
    status, body = request("/api/signin", {"identifier": "absent-pro-api", "password": "wrong"})
    check("failed login is generic and creates no session",
          status == 401 and body == {"error": "Invalid credentials"} and state_hash() == before)
finally:
    print(json.dumps({"scope": "local partial Pro artifact, not official evaluation",
                      "checks": checks, "concurrency": rows,
                      "passed": sum(item["passed"] for item in checks), "total": len(checks)}, indent=2))
