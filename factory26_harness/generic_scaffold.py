"""Task-neutral runnable foundation for the Factory26 qualifier.

No product-specific screen, seed, route, workflow, or API is shipped here.
The coding agent must create those from the supplied requirements.
"""

from __future__ import annotations

import json
from pathlib import Path


FRONTEND_PACKAGE = {
    "name": "generated-frontend",
    "private": True,
    "type": "module",
    "scripts": {"build": "node build.mjs"},
}
BACKEND_PACKAGE = {
    "name": "generated-backend",
    "private": True,
    "type": "module",
    "scripts": {"start": "node server.mjs"},
}

BUILD_SCRIPT = '''import { cp, mkdir, rm } from "node:fs/promises";
import path from "node:path";

const source = path.resolve("src");
const target = path.resolve("dist");
await rm(target, { recursive: true, force: true });
await mkdir(target, { recursive: true });
await cp(source, target, { recursive: true });
'''

INDEX_HTML = '''<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Application</title>
    <link rel="stylesheet" href="/styles.css" />
  </head>
  <body>
    <main id="app"></main>
    <script type="module" src="/app.js"></script>
  </body>
</html>
'''

SERVER_MJS = r'''import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.resolve(here, "../frontend/dist");
const port = Number.parseInt(process.env.PORT || "3000", 10);
const host = process.env.HOST || "0.0.0.0";
const types = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
};

createServer(async (request, response) => {
  try {
    const url = new URL(request.url || "/", "http://localhost");
    if (url.pathname === "/api/health") {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({ ready: true }));
      return;
    }
    const requested = url.pathname === "/" ? "index.html" : url.pathname.replace(/^\/+/, "");
    const candidate = path.resolve(publicDir, requested);
    const safePath = candidate.startsWith(publicDir + path.sep)
      ? candidate : path.join(publicDir, "index.html");
    let filePath = safePath;
    let body;
    try {
      body = await readFile(filePath);
    } catch {
      filePath = path.join(publicDir, "index.html");
      body = await readFile(filePath);
    }
    response.writeHead(200, { "content-type": types[path.extname(filePath)] || "application/octet-stream" });
    response.end(body);
  } catch (error) {
    response.writeHead(500, { "content-type": "application/json" });
    response.end(JSON.stringify({ error: String(error.message || error) }));
  }
}).listen(port, host);
'''

STORAGE_MJS = '''import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";

const dataPath = path.join(path.dirname(fileURLToPath(import.meta.url)), "data", "state.json");
let previousWrite = Promise.resolve();

export async function loadState() {
  return JSON.parse(await readFile(dataPath, "utf8"));
}

export async function saveState(next) {
  await mkdir(path.dirname(dataPath), { recursive: true });
  const temporary = `${dataPath}.${randomUUID()}.tmp`;
  await writeFile(temporary, JSON.stringify(next));
  await rename(temporary, dataPath);
  return next;
}

// Single-process transaction: check mutable-state invariants INSIDE updater,
// against its fresh state, before mutation. Earlier loadState snapshots can race.
// Throw to reject without persisting; send HTTP responses after awaiting this call.
export function updateState(updater) {
  const task = previousWrite.then(async () => {
    const current = await loadState();
    const next = await updater(structuredClone(current));
    if (next === undefined) throw new Error("state updater returned undefined");
    return saveState(next);
  });
  previousWrite = task.catch(() => {});
  return task;
}
'''

HTTP_MJS = '''export async function readJsonBody(request, maximumBytes = 1_000_000) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > maximumBytes) throw new Error("request body too large");
    chunks.push(chunk);
  }
  if (!chunks.length) return {};
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

export function sendJson(response, status, body) {
  response.writeHead(status, { "content-type": "application/json; charset=utf-8" });
  response.end(JSON.stringify(body));
}
'''

API_JS = '''export async function requestJson(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "content-type": "application/json", ...(options.headers || {}) },
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `Request failed: ${response.status}`);
  return result;
}
'''


def scaffold_workspace(root: Path) -> list[str]:
    """Create only generic runtime files; never copy a task-specific template."""
    files = {
        "frontend/package.json": json.dumps(FRONTEND_PACKAGE, indent=2) + "\n",
        "frontend/build.mjs": BUILD_SCRIPT,
        "frontend/src/index.html": INDEX_HTML,
        "frontend/src/app.js": "// The coding agent implements the requested application here.\n",
        "frontend/src/api.js": API_JS,
        "frontend/src/styles.css": "/* The coding agent implements the requested styling here. */\n",
        "backend/package.json": json.dumps(BACKEND_PACKAGE, indent=2) + "\n",
        "backend/server.mjs": SERVER_MJS,
        "backend/storage.mjs": STORAGE_MJS,
        "backend/http.mjs": HTTP_MJS,
        "backend/data/state.json": "{}\n",
    }
    created: list[str] = []
    for relative, content in files.items():
        destination = root / relative
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        created.append(relative)
    return created
