"""A frozen generated suite must reject a reachable empty UI, not merely 200.

No app and no credentials are supplied. Run in an isolated no-network container.
This necessary negative control does not establish semantic test completeness.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from grade import manifest, summarize


class Blank(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(b'<!doctype html><html><body></body></html>')

    def log_message(self, *_args):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('frozen', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    frozen = json.loads((args.frozen / 'frozen.json').read_text())
    before = manifest(args.frozen / 'suite')
    if before != frozen['tests_sha256']:
        raise RuntimeError('frozen test source changed')
    args.output.mkdir(parents=True, exist_ok=False)
    server = ThreadingHTTPServer(('127.0.0.1', 3000), Blank)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    result = {'kind': 'internal_blank_ui_negative_control', 'gate': False}
    try:
        with tempfile.TemporaryDirectory(prefix='acceptance-blank-') as tmp:
            suite = Path(tmp) / 'suite'
            shutil.copytree(args.frozen / 'suite', suite)
            (suite / 'node_modules').symlink_to('/opt/arcbench/node_modules')
            config = suite / 'playwright.config.cjs'
            config.write_text("module.exports={testDir:'.',testMatch:'**/*.spec.ts',timeout:6000,"
                "expect:{timeout:2000},retries:0,workers:1,reporter:[['json']],"
                "use:{baseURL:'http://127.0.0.1:3000',actionTimeout:2000}}")
            proc = subprocess.run(['/opt/arcbench/node_modules/.bin/playwright', 'test', '-c', str(config)],
                capture_output=True, text=True, timeout=30 + frozen['expected'] * 7)
            (args.output / 'playwright.json').write_text(proc.stdout)
            (args.output / 'stderr.txt').write_text(proc.stderr)
            report = json.loads(proc.stdout)
            result.update(summarize(report), test_exit=proc.returncode)
            result['gate'] = (proc.returncode == 1 and result['passed'] == 0 and
                result['failed'] == frozen['expected'] and result['total'] == frozen['expected']
                and not result['skipped'] and not result['flaky'] and not result['errors'])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        result['tests_unchanged'] = before == manifest(args.frozen / 'suite')
        result['server_cleaned'] = not thread.is_alive()
        result['gate'] = result['gate'] and result['tests_unchanged'] and result['server_cleaned']
        (args.output / 'verdict.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)
    return 0 if result['gate'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
