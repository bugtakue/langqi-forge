import { createServer } from "node:http";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.resolve(here, "../frontend/dist");
const dataDir = path.resolve(here, "data");
const statePath = path.join(dataDir, "state.json");
const port = Number.parseInt(process.env.PORT || "3000", 10);
const host = process.env.HOST || "0.0.0.0";
let ready = false;

await mkdir(dataDir, { recursive: true });
try {
  await readFile(statePath, "utf8");
} catch {
  await writeFile(statePath, JSON.stringify({ requests: [] }, null, 2));
}
ready = true;

async function readState() {
  const state = JSON.parse(await readFile(statePath, "utf8"));
  // Ensure requests array exists in state
  if (!state.requests) {
    state.requests = [];
  }
  return state;
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
      const body = await readJsonBody(request);
      // Ensure requests array exists in the updated state
      const next = { 
        ...previous, 
        ...(body || {})
      };
      // Always ensure requests array exists
      if (!next.requests) {
        next.requests = previous.requests || [];
      }
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

server.listen(port, host, () => console.log(`listening on ${host}:${port}`));
