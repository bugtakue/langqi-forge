"""Local API diagnosis of our own in-progress artifact, not an official test."""
import concurrent.futures
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from factory26_harness.checks import _port_available, _safe_environment

if len(sys.argv) != 2:
    raise SystemExit('Supply template/ inside a disposable factory26-api-check.* directory.')
ROOT = Path(sys.argv[1]).resolve()
if not any(parent.name.startswith('factory26-api-check.') for parent in ROOT.parents):
    raise SystemExit('Only disposable factory26-api-check.* copies are allowed.')
PORT = 19431
BASE = f'http://127.0.0.1:{PORT}'
results = []
server = None


def request(path, data=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(BASE + path, headers=headers,
        data=json.dumps(data).encode() if data is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def check(name, ok):
    results.append({'check': name, 'passed': bool(ok)})
    if not ok:
        raise AssertionError(name)


def start():
    global server
    if not _port_available(PORT):
        raise RuntimeError('diagnostic port is occupied')
    server = subprocess.Popen(['node', 'server.mjs'], cwd=ROOT / 'backend',
        env=_safe_environment(PORT=str(PORT), HOST='127.0.0.1'),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            if request('/api/health')[0] == 200:
                return
        except (OSError, urllib.error.URLError):
            if server.poll() is not None:
                raise RuntimeError('diagnostic server exited')
        time.sleep(.1)
    raise RuntimeError('diagnostic server not healthy')


def stop():
    global server
    if server is not None:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
        server = None


try:
    start()
    username = 'local-probe-' + str(time.time_ns())[-10:]
    email = username + '@example.test'
    password = 'Local-probe-strong-123!'
    changed_password = 'Local-probe-changed-456!'
    registration = {'username': username, 'email': email, 'password': password,
                    'confirmPassword': password, 'agreeToTerms': True}
    status, body = request('/api/register', registration)
    check('registration creates a public account', status == 201 and body['account']['username'] == username)
    check('registration response excludes password material', set(body['account']) == {'id', 'username', 'email'})
    check('duplicate registration is rejected', request('/api/register', registration)[0] == 400)
    check('wrong password is rejected', request('/api/signin', {'usernameOrEmail': username, 'password': 'wrong'})[0] == 401)
    status, body = request('/api/signin', {'usernameOrEmail': email, 'password': password})
    check('email login works', status == 200 and isinstance(body.get('sessionId'), str))
    token = body['sessionId']
    check('current session resolves owner', request('/api/me', token=token)[1]['account']['username'] == username)
    stop()
    start()
    check('account and session persist over process restart', request('/api/me', token=token)[1]['account']['email'] == email)
    status, _ = request('/api/signout', {'sessionId': token})
    check('signout revokes session', status == 200 and request('/api/me', token=token)[0] == 401)
    recovery = {'email': email, 'code': 'wrong', 'newPassword': changed_password, 'confirmPassword': changed_password}
    check('wrong recovery code is rejected', request('/api/recover', recovery)[0] == 400)
    check('rejected recovery preserves existing credential', request('/api/signin', {'usernameOrEmail': username, 'password': password})[0] == 200)
    recovery['code'] = '123456'
    check('fixture recovery succeeds', request('/api/recover', recovery)[0] == 200)
    check('old credential stops working', request('/api/signin', {'usernameOrEmail': username, 'password': password})[0] == 401)
    stop()
    start()
    check('new credential persists over restart', request('/api/signin', {'usernameOrEmail': username, 'password': changed_password})[0] == 200)
    concurrent_registration = dict(registration, username=username+'-race', email='race-'+email)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: request('/api/register', concurrent_registration)[0], range(2)))
    check('simultaneous duplicate writes commit only once', sorted(responses) == [201, 400])
finally:
    stop()
    print(json.dumps({'scope': 'own partial artifact API-only, not official GUI', 'checks': results,
                      'passed': sum(r['passed'] for r in results), 'total': len(results)}, ensure_ascii=False))
