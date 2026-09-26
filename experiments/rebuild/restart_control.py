"""Grader-owned process restart; never an application endpoint or model tool."""
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class AppProcess:
    def __init__(self, cwd: Path, env: dict, log: Path, identity=None):
        self.cwd, self.env, self.log = cwd, env, log
        self.identity = identity
        self.process = None
        self.restarts = 0
        self.lock = threading.Lock()

    @staticmethod
    def port_open():
        with socket.socket() as probe:
            return probe.connect_ex(('127.0.0.1', 3000)) == 0

    def start(self):
        if self.port_open():
            raise RuntimeError('port already occupied before controlled start')
        with self.log.open('a') as stream:
            privileges = {'user':self.identity, 'group':self.identity, 'extra_groups':[]} if self.identity else {}
            self.process = subprocess.Popen(['npm', 'run', 'start'], cwd=self.cwd, env=self.env,
                stdout=stream, stderr=subprocess.STDOUT, start_new_session=True, **privileges)
        for _ in range(80):
            if self.process.poll() is not None:
                raise RuntimeError('application exited during startup')
            if self.port_open():
                return
            time.sleep(.25)
        raise RuntimeError('application did not bind port 3000')

    def stop(self):
        if self.process is None:
            return
        process = self.process
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            pass
        # npm can exit before its child; kill the entire known process group.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
        self.process = None
        for _ in range(40):
            if not self.port_open():
                return
            time.sleep(.05)
        raise RuntimeError('application port survived process cleanup')

    def restart(self):
        with self.lock:
            self.stop()
            self.start()
            self.restarts += 1


class RestartServer(ThreadingHTTPServer):
    def __init__(self, process):
        super().__init__(('127.0.0.1', 0), RestartHandler)
        self.app_process = process
        self.secret = secrets.token_urlsafe(24)


class RestartHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        if self.path != '/restart' or not secrets.compare_digest(
                self.headers.get('X-Grader-Token', ''), self.server.secret):
            self.send_error(403)
            return
        try:
            self.server.app_process.restart()
            status, payload = 200, {'restarted': True}
        except Exception:
            status, payload = 500, {'restarted': False}
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class RestartControl:
    def __init__(self, process):
        self.server = RestartServer(process)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return {
            'E2E_RESTART_CONTROL_URL': f'http://127.0.0.1:{self.server.server_port}/restart',
            'E2E_RESTART_CONTROL_TOKEN': self.server.secret,
        }

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
