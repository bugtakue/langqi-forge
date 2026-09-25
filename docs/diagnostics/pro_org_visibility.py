"""Read-only repository checks against the reviewed, isolated generated fixture.

Only the synthetic sign-in writes its local session. Never target a remote app.
"""
import hashlib
import http.cookiejar
import json
import pathlib
import sys
import urllib.error
import urllib.request


BASE = "http://127.0.0.1:19438"
EXPECTED_SERVER = "9c22bc37924a880c2b12e748880cc0a54b093a0b0e1faba943fe96704e936322"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("local fixture must not redirect")


def main():
    root = pathlib.Path(sys.argv[1]).resolve(strict=True)
    assert root.name == "template" and root.parent.name.startswith("factory26-pro-org.")
    assert root.parent.parent == pathlib.Path("/private/tmp")
    server = root / "backend/server.mjs"
    assert hashlib.sha256(server.read_bytes()).hexdigest() == EXPECTED_SERVER
    state = root / "backend/data/state.json"
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect(),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
    )
    passed = []

    def check(name, condition):
        assert condition, name
        passed.append(name)

    def request(route, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(BASE + route, data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            response = opener.open(req, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read(100_000))

    def digest():
        return hashlib.sha256(state.read_bytes()).hexdigest()

    def inspect_visibility(actor):
        before = digest()
        status, body = request("/api/orgs/acme-demo")
        check(actor + ": list exposes only public repository", status == 200 and
              [row["name"] for row in body["repositories"]] == ["acme-docs"] and
              "acme-secrets" not in json.dumps(body))
        status, body = request("/api/repos/acme-demo/acme-docs")
        check(actor + ": public detail", status == 200 and
              body["repository"]["name"] == "acme-docs" and
              body["repository"]["visibility"] == "public")
        status, body = request("/api/repos/acme-demo/acme-secrets")
        check(actor + ": private direct access denied", status == 404 and
              body == {"error": "Repository not found or access denied"})
        check(actor + ": reads leave persisted state unchanged", digest() == before)

    status, body = request("/api/health")
    check("local health", status == 200 and body == {"ready": True})
    inspect_visibility("visitor")
    # Public task fixture credential, never a real user credential.
    status, body = request("/api/signin", {
        "identifier": "alice-dev", "password": "Valid-password-123!",
    })
    check("public synthetic account sign-in", status == 200 and
          body == {"user": {"username": "alice-dev"}})
    inspect_visibility("signed-in account without private grant")
    print(json.dumps({"passed": len(passed), "checks": passed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
