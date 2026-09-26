"""Local experiment gateway. No secrets on disk, no retry after uncertainty.

Only the organizer's fixed Chat Completions endpoint is reachable. Run agents
on a Docker internal network, this gateway on both internal and bridge networks.
The control token is NOT supplied to agents. SQLite transactions reserve money
before outbound IO; a crash/ambiguous result retains the reservation and locks
the campaign. Costs here are conservative uncached bounds, not official bills.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.error
import urllib.request

MODEL = "glm-5.3-flash"
UPSTREAM = "https://api.arc-bench.com/v1/chat/completions"
PHASES = {"baseline": 20, "mechanism": 20, "formal": 60, "reserve": 20}
MICRO = 1_000_000


class BudgetDenied(ValueError):
    pass


def request_bound(payload: dict) -> tuple[bytes, int, int]:
    if payload.get("model") != MODEL or payload.get("stream") is True:
        raise BudgetDenied("unpriced model or streaming request")
    messages = payload.get("messages")
    if not isinstance(messages, list) or not 1 <= len(messages) <= 600:
        raise BudgetDenied("invalid messages")
    for msg in messages:
        if not isinstance(msg, dict) or not isinstance(msg.get("content", "") or "", str):
            raise BudgetDenied("only priced text messages are permitted")
    maximum = payload.get("max_tokens", payload.get("max_completion_tokens"))
    if type(maximum) is not int or not 1 <= maximum <= 32768:
        raise BudgetDenied("explicit bounded output limit is required")
    if payload.get("n", 1) != 1 or any(k in payload for k in ("audio", "modalities", "web_search_options")):
        raise BudgetDenied("unpriced request options")
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    if len(body) > 512_000:
        raise BudgetDenied("request byte limit")
    # Text-only byte-level tokenization: twice the ENTIRE serialized UTF-8
    # request, plus per-message framing and 32K fixed allowance. No cache
    # discount is assumed. Response usage must validate this conservative bound.
    prompt_bound = len(body) * 2 + len(messages) * 128 + 32768
    return body, prompt_bound, maximum


def micro_cost(prompt: int, completion: int) -> int:
    # 0.8 / 2.8 CNY per million => 0.8 / 2.8 micro-CNY per token.
    return (prompt * 8 + completion * 28 + 9) // 10


class Ledger:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS trials (
                  id TEXT PRIMARY KEY, phase TEXT NOT NULL, cap INTEGER NOT NULL,
                  deadline REAL NOT NULL, token_hash TEXT UNIQUE NOT NULL, closed INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS calls (
                  id TEXT PRIMARY KEY, trial TEXT NOT NULL, status TEXT NOT NULL,
                  reserve INTEGER NOT NULL, charged INTEGER NOT NULL, prompt_bound INTEGER NOT NULL,
                  output_bound INTEGER NOT NULL, prompt_tokens INTEGER, completion_tokens INTEGER,
                  created REAL NOT NULL, finished REAL, payload_sha TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS call_failures (
                  call_id TEXT NOT NULL, created REAL NOT NULL, error_type TEXT NOT NULL,
                  http_status INTEGER, evidence_saved INTEGER NOT NULL);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level="IMMEDIATE")
        db.row_factory = sqlite3.Row
        return db

    def create_trial(self, name: str, phase: str, cap: float, seconds: int) -> str:
        if phase not in PHASES or not 0 < cap <= PHASES[phase] or not 1 <= seconds <= 3600:
            raise BudgetDenied("invalid trial allocation")
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM trials WHERE closed=0").fetchone():
                raise BudgetDenied("another trial remains open")
            if db.execute("SELECT 1 FROM calls WHERE status!='settled'").fetchone():
                raise BudgetDenied("unsettled reservation; reconcile before continuing")
            db.execute("INSERT INTO trials(id,phase,cap,deadline,token_hash) VALUES(?,?,?,?,?)",
                       (name, phase, round(cap * MICRO), time.time() + seconds, hashlib.sha256(token.encode()).hexdigest()))
        return token

    def reserve(self, token: str, payload: dict) -> tuple[str, bytes]:
        body, prompt, output = request_bound(payload)
        reserve = micro_cost(prompt, output)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            trial = db.execute("SELECT * FROM trials WHERE token_hash=? AND closed=0",
                               (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
            if not trial or time.time() >= trial["deadline"]:
                raise BudgetDenied("unknown, closed or expired trial")
            if db.execute("SELECT 1 FROM calls WHERE status!='settled'").fetchone():
                raise BudgetDenied("another request active or unresolved; no retries")
            total = db.execute("SELECT COALESCE(SUM(charged),0) FROM calls").fetchone()[0]
            phase = db.execute("SELECT COALESCE(SUM(c.charged),0) FROM calls c JOIN trials t ON t.id=c.trial WHERE t.phase=?", (trial["phase"],)).fetchone()[0]
            local = db.execute("SELECT COALESCE(SUM(charged),0) FROM calls WHERE trial=?", (trial["id"],)).fetchone()[0]
            # The verified practice balance is 100. Formal runs are not sent
            # through this local gateway; importing their bills is a separate gate.
            if total + reserve > min(120, 100) * MICRO or phase + reserve > PHASES[trial["phase"]] * MICRO or local + reserve > trial["cap"]:
                raise BudgetDenied("maximum request cost cannot be reserved")
            rid = secrets.token_hex(16)
            db.execute("INSERT INTO calls(id,trial,status,reserve,charged,prompt_bound,output_bound,created,payload_sha) VALUES(?,?,?,?,?,?,?,?,?)",
                       (rid, trial["id"], "reserved", reserve, reserve, prompt, output, time.time(), hashlib.sha256(body).hexdigest()))
        return rid, body

    def settle(self, rid: str, response: dict):
        usage = response.get("usage", {})
        prompt, output = usage.get("prompt_tokens"), usage.get("completion_tokens")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM calls WHERE id=? AND status='reserved'", (rid,)).fetchone()
            if not row:
                raise BudgetDenied("reservation not active")
            if (type(prompt) is not int or type(output) is not int or min(prompt, output) < 0
                    or prompt > row["prompt_bound"] or output > row["output_bound"]
                    or not response.get("choices")):
                # Transaction rollback leaves the full reservation charged.
                raise BudgetDenied("usage missing or exceeds bound; locked for reconciliation")
            db.execute("UPDATE calls SET status='settled', charged=?, prompt_tokens=?, completion_tokens=?, finished=? WHERE id=?",
                       (micro_cost(prompt, output), prompt, output, time.time(), rid))

    def close_trial(self, name: str):
        with self.connect() as db:
            db.execute("UPDATE trials SET closed=1 WHERE id=?", (name,))

    def record_failure(self, rid: str, exc: Exception, evidence_saved: bool):
        # Diagnostic metadata only. This does NOT settle or release any money.
        status = exc.code if isinstance(exc, urllib.error.HTTPError) else None
        with self.connect() as db:
            db.execute('INSERT INTO call_failures VALUES(?,?,?,?,?)',
                       (rid, time.time(), type(exc).__name__, status, int(evidence_saved)))

    def status(self):
        with self.connect() as db:
            return {"currency": "CNY", "cost_kind": "uncached_usage_upper_bound_not_official_bill",
                    "total_cny": db.execute("SELECT COALESCE(SUM(charged),0)/1000000.0 FROM calls").fetchone()[0],
                    "calls": [dict(r) for r in db.execute("SELECT id,trial,status,reserve,charged,prompt_tokens,completion_tokens FROM calls")],
                    "failures": [dict(r) for r in db.execute('SELECT * FROM call_failures')],
                    "trials": [dict(r) for r in db.execute("SELECT id,phase,cap,deadline,closed FROM trials")]}


class Gateway(ThreadingHTTPServer):
    def __init__(self, address, ledger, control):
        super().__init__(address, Handler)
        self.ledger, self.control = ledger, control
        self.key = None
        self.transport_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Never log auth headers, request bodies, URL tokens or model text.

    def reply(self, status, value, kind="application/json"):
        raw = value.encode() if isinstance(value, str) else json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/health":
            return self.reply(200, {"ready": bool(self.server.key)})
        if self.path == "/credential":
            # No key reflected into the DOM after submission. Control token is
            # entered separately and never exposed to candidate containers.
            return self.reply(200, """<!doctype html><html><meta charset=utf-8>
<title>Factory26 organizer credential handoff</title>
<h1>Local, memory-only credential handoff</h1>
<form id=f><label>Local control file <input id=control type=file></label>
<label>Organizer practice key <input id=key type=password autocomplete=off></label>
<button>Load once</button></form><p id=status></p><script>
f.onsubmit=async e=>{e.preventDefault();const r=await fetch('/credential',{method:'POST',
headers:{'Content-Type':'application/json','X-Control':await control.files[0].text()},body:JSON.stringify({key:key.value})});
key.value='';control.value='';document.querySelector('#status').textContent=r.ok?'Loaded in memory':'Rejected';
if(r.ok)f.remove()};</script></html>""", "text/html; charset=utf-8")
        self.reply(404, {"error": "not found"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 512000 or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise BudgetDenied("bounded JSON required")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise BudgetDenied("JSON object required")
            if self.path == "/v1/chat/completions":
                return self.completion(payload)
            if not secrets.compare_digest(self.headers.get("X-Control", ""), self.server.control):
                return self.reply(403, {"error": "control authentication required"})
            if self.path == "/credential":
                if self.server.key or not isinstance(payload.get("key"), str) or len(payload["key"]) < 16:
                    raise BudgetDenied("credential already loaded or invalid")
                self.server.key = payload["key"]
                return self.reply(200, {"loaded": True})
            if self.path == "/trial":
                token = self.server.ledger.create_trial(payload["id"], payload["phase"], payload["cap_cny"], payload["seconds"])
                return self.reply(200, {"token": token})
            if self.path == "/close":
                self.server.ledger.close_trial(payload["id"])
                return self.reply(200, {"closed": True})
            if self.path == "/status":
                return self.reply(200, self.server.ledger.status())
            self.reply(404, {"error": "not found"})
        except (BudgetDenied, KeyError, TypeError, ValueError, sqlite3.IntegrityError):
            self.reply(402, {"error": {"message": "Local budget or request gate denied; inspect local ledger"}})

    def completion(self, payload):
        if not self.server.key:
            raise BudgetDenied("organizer credential not loaded")
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise BudgetDenied("trial token missing")
        rid, body = self.server.ledger.reserve(auth[7:], payload)
        trace_dir = self.server.ledger.path.parent / 'traces'
        trace_dir.mkdir(exist_ok=True)
        def evidence(suffix, raw):
            # Only JSON bodies, never headers. Both upstream and scoped tokens
            # are redacted even if a generated message accidentally quotes one.
            safe = raw.decode('utf-8', errors='replace').replace(self.server.key, '[REDACTED]').replace(auth[7:], '[TRIAL_TOKEN]')
            with (trace_dir / (rid + '.' + suffix + '.json')).open('x') as stream:
                stream.write(safe)
        evidence('request', body)
        req = urllib.request.Request(UPSTREAM, data=body, headers={
            "Content-Type": "application/json", "Authorization": "Bearer " + self.server.key})
        try:
            # No retry; all uncertain errors keep the full reservation. Do not
            # reflect arbitrary provider errors or credentials to candidates.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=240) as reply:
                raw = reply.read(8_000_001)
            if len(raw) > 8_000_000:
                raise BudgetDenied("response too large")
            # Preserve the received response BEFORE settlement. Missing usage
            # and non-JSON provider errors need evidence too, not just a 402.
            evidence('response', raw)
            data = json.loads(raw)
            self.server.ledger.settle(rid, data)
            return self.reply(200, data)
        except Exception as exc:
            saved = False
            try:
                diagnostic = {'error_type': type(exc).__name__,
                              'http_status': exc.code if isinstance(exc, urllib.error.HTTPError) else None}
                if isinstance(exc, urllib.error.HTTPError):
                    # Provider error text stays in the private redacted trace,
                    # never forwarded to the candidate or interpreted as orders.
                    diagnostic['provider_body'] = exc.read(16000).decode('utf-8', errors='replace')
                evidence('error', json.dumps(diagnostic).encode())
                saved = True
            except Exception:
                # An evidence disk failure must not produce a successful bill
                # settlement or silently reopen the spending circuit.
                pass
            finally:
                self.server.ledger.record_failure(rid, exc, saved)
            return self.reply(402, {"error": {"message": "Uncertain upstream result; full reservation retained, campaign locked"}})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8021)
    args = parser.parse_args()
    args.state.mkdir(parents=True, exist_ok=True)
    control = secrets.token_urlsafe(32)
    path = args.state / "control.token"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(control)
    server = Gateway(("0.0.0.0", args.port), Ledger(args.state / "budget.sqlite"), control)
    print("Gateway ready; load organizer credential via loopback-only published port", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
