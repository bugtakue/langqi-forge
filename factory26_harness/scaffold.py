from __future__ import annotations

import json
import shutil
from pathlib import Path


FRONTEND_PACKAGE = {
    "name": "factory26-generated-frontend",
    "private": True,
    "version": "0.0.0",
    "type": "module",
    "scripts": {"build": "node build.mjs"},
}

BACKEND_PACKAGE = {
    "name": "factory26-generated-backend",
    "private": True,
    "version": "0.0.0",
    "type": "module",
    "scripts": {"start": "node server.mjs"},
}

BUILD_SCRIPT = r'''import { cp, mkdir, rm } from "node:fs/promises";
import path from "node:path";

const source = path.resolve("src");
const target = path.resolve("dist");
await rm(target, { recursive: true, force: true });
await mkdir(target, { recursive: true });
await cp(source, target, { recursive: true });
console.log("frontend built");
'''

INDEX_HTML = r'''<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Generated application</title>
    <link rel="stylesheet" href="/styles.css" />
  </head>
  <body>
    <header class="app-header">
      <a class="brand" href="/">Generated application</a>
      <nav aria-label="Primary navigation">
        <button type="button" id="refresh-button">Refresh</button>
      </nav>
    </header>
    <main id="app" class="app-shell">
      <h1>Application workspace</h1>
      <p id="status" role="status">Ready</p>
      <section class="panel" aria-labelledby="starter-heading">
        <h2 id="starter-heading">Starter item</h2>
        <form id="starter-form" novalidate>
          <label for="starter-name">Name</label>
          <input id="starter-name" name="name" type="text" autocomplete="off" />
          <p id="starter-error" class="error" role="alert"></p>
          <button type="submit">Save</button>
        </form>
        <ul id="starter-list" aria-label="Saved items"></ul>
      </section>
    </main>
    <script type="module" src="/app.js"></script>
  </body>
</html>
'''

APP_JS = r'''const statusNode = document.querySelector("#status");
const form = document.querySelector("#starter-form");
const input = document.querySelector("#starter-name");
const errorNode = document.querySelector("#starter-error");
const list = document.querySelector("#starter-list");

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "content-type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json();
}

function render(state) {
  list.replaceChildren();
  for (const item of state.items || []) {
    const row = document.createElement("li");
    row.textContent = item.name;
    list.append(row);
  }
}

async function load() {
  statusNode.textContent = "Loading";
  try {
    render(await request("/api/state"));
    statusNode.textContent = "Ready";
  } catch (error) {
    statusNode.textContent = error.message;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = input.value.trim();
  errorNode.textContent = name ? "" : "Name is required";
  if (!name) return;
  const current = await request("/api/state");
  const items = [...(current.items || []), { id: crypto.randomUUID(), name }];
  render(await request("/api/state", { method: "PUT", body: JSON.stringify({ items }) }));
  input.value = "";
  statusNode.textContent = "Saved";
});

document.querySelector("#refresh-button").addEventListener("click", load);
load();
'''

STYLES_CSS = r''':root {
  color: #1f2937;
  background: #f3f4f6;
  font: 16px/1.5 system-ui, sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; }
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  background: #111827;
  color: white;
}
.brand { color: inherit; font-weight: 700; text-decoration: none; }
.app-shell { width: min(70rem, calc(100% - 2rem)); margin: 2rem auto; }
.panel { max-width: 42rem; padding: 1.25rem; border-radius: .75rem; background: white; box-shadow: 0 1px 5px #0002; }
form { display: grid; gap: .5rem; }
input, button { min-height: 2.5rem; padding: .55rem .75rem; font: inherit; }
button { cursor: pointer; }
.error { min-height: 1.5rem; margin: 0; color: #b91c1c; }
'''

SERVER_MJS = r'''import { createServer } from "node:http";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.resolve(here, "../frontend/dist");
const dataDir = path.resolve(here, "data");
const statePath = path.join(dataDir, "state.json");
const port = Number.parseInt(process.env.PORT || "3000", 10);
let ready = false;

await mkdir(dataDir, { recursive: true });
try {
  await readFile(statePath, "utf8");
} catch {
  await writeFile(statePath, JSON.stringify({ items: [] }, null, 2));
}
ready = true;

async function readState() {
  return JSON.parse(await readFile(statePath, "utf8"));
}

async function readJsonBody(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  if (!chunks.length) return {};
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

function sendJson(response, status, value) {
  response.writeHead(status, { "content-type": "application/json; charset=utf-8" });
  response.end(JSON.stringify(value));
}

const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
};

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url || "/", `http://${request.headers.host || "localhost"}`);
    if (url.pathname === "/api/health") {
      return sendJson(response, ready ? 200 : 503, { ready });
    }
    if (url.pathname === "/api/state" && request.method === "GET") {
      return sendJson(response, 200, await readState());
    }
    if (url.pathname === "/api/state" && ["PUT", "POST"].includes(request.method || "")) {
      const previous = await readState();
      const next = { ...previous, ...(await readJsonBody(request)) };
      const temporary = `${statePath}.tmp`;
      await writeFile(temporary, JSON.stringify(next, null, 2));
      await import("node:fs/promises").then(({ rename }) => rename(temporary, statePath));
      return sendJson(response, 200, next);
    }
    const requested = url.pathname === "/" ? "index.html" : url.pathname.replace(/^\/+/, "");
    let resolved = path.resolve(publicDir, requested);
    if (!resolved.startsWith(publicDir + path.sep)) resolved = path.join(publicDir, "index.html");
    let body;
    try {
      body = await readFile(resolved);
    } catch {
      resolved = path.join(publicDir, "index.html");
      body = await readFile(resolved);
    }
    response.writeHead(200, { "content-type": contentTypes[path.extname(resolved)] || "application/octet-stream" });
    response.end(body);
  } catch (error) {
    sendJson(response, 500, { error: error.message });
  }
});

server.listen(port, "127.0.0.1", () => console.log(`listening on ${port}`));
'''


def _write_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _copy_template(root: Path, domain: str) -> list[str]:
    template_root = Path(__file__).resolve().parent / "templates" / domain
    if not template_root.is_dir():
        return []
    created: list[str] = []
    for source in sorted(template_root.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(template_root)
        destination = root / relative
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        created.append(str(relative))
    return created


def scaffold_workspace(root: Path, domain: str = "generic") -> list[str]:
    templated = _copy_template(root, domain)
    if templated:
        return templated
    files = {
        root / "frontend" / "package.json": json.dumps(FRONTEND_PACKAGE, indent=2) + "\n",
        root / "frontend" / "build.mjs": BUILD_SCRIPT,
        root / "frontend" / "src" / "index.html": INDEX_HTML,
        root / "frontend" / "src" / "app.js": APP_JS,
        root / "frontend" / "src" / "styles.css": STYLES_CSS,
        root / "backend" / "package.json": json.dumps(BACKEND_PACKAGE, indent=2) + "\n",
        root / "backend" / "server.mjs": SERVER_MJS,
    }
    return [str(path.relative_to(root)) for path, content in files.items() if _write_missing(path, content)]
