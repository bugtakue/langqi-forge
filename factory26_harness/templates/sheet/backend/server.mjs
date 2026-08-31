import { createServer } from "node:http";
import { randomUUID } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.resolve(here, "../frontend/dist");
const dataDir = path.join(here, "data");
const statePath = path.join(dataDir, "sheet-state.json");
const port = Number.parseInt(process.env.PORT || "3000", 10);
let ready = false;
let state = { workbooks: [] };
let persistence = Promise.resolve();

await mkdir(dataDir, { recursive: true });
try {
  const loaded = JSON.parse(await readFile(statePath, "utf8"));
  if (Array.isArray(loaded.workbooks)) state = loaded;
} catch {
  await writeFile(statePath, JSON.stringify(state, null, 2));
}
ready = true;

function persist() {
  const snapshot = JSON.stringify(state, null, 2);
  persistence = persistence.then(async () => {
    const temporary = `${statePath}.tmp`;
    await writeFile(temporary, snapshot);
    await rename(temporary, statePath);
  });
  return persistence;
}

function sendJson(response, status, value) {
  response.writeHead(status, { "content-type": "application/json; charset=utf-8" });
  response.end(JSON.stringify(value));
}

async function body(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  if (!chunks.length) return {};
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

function newWorkbook(name = "Untitled workbook", cells = {}) {
  const now = new Date().toISOString();
  return {
    id: randomUUID(),
    name,
    createdAt: now,
    updatedAt: now,
    activeSheetId: "sheet-1",
    sheets: [
      {
        id: "sheet-1",
        name: "Sheet1",
        cells,
        validations: {},
        selected: "A1",
        selection: ["A1"],
      },
    ],
  };
}

function matchWorkbook(pathname) {
  const match = /^\/api\/workbooks\/([^/]+)$/.exec(pathname);
  if (!match) return null;
  return state.workbooks.find((item) => item.id === decodeURIComponent(match[1])) || null;
}

const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
};

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url || "/", `http://${request.headers.host || "localhost"}`);
    if (url.pathname === "/api/health") {
      return sendJson(response, ready ? 200 : 503, { ready });
    }
    if (url.pathname === "/api/workbooks" && request.method === "GET") {
      return sendJson(
        response,
        200,
        state.workbooks.map(({ id, name, updatedAt }) => ({ id, name, updatedAt })),
      );
    }
    if (url.pathname === "/api/workbooks" && request.method === "POST") {
      const payload = await body(request);
      const workbook = newWorkbook(String(payload.name || "Untitled workbook"), payload.cells || {});
      state.workbooks.push(workbook);
      await persist();
      return sendJson(response, 201, workbook);
    }
    const workbook = matchWorkbook(url.pathname);
    if (workbook && request.method === "GET") {
      return sendJson(response, 200, workbook);
    }
    if (workbook && request.method === "PUT") {
      const payload = await body(request);
      const replacement = {
        ...payload,
        id: workbook.id,
        createdAt: workbook.createdAt,
        updatedAt: new Date().toISOString(),
      };
      state.workbooks[state.workbooks.indexOf(workbook)] = replacement;
      await persist();
      return sendJson(response, 200, replacement);
    }
    if (url.pathname.startsWith("/api/")) {
      return sendJson(response, 404, { error: "Not found" });
    }

    const requested = url.pathname === "/" ? "index.html" : url.pathname.replace(/^\/+/, "");
    let resolved = path.resolve(publicDir, requested);
    if (!resolved.startsWith(publicDir + path.sep)) resolved = path.join(publicDir, "index.html");
    let data;
    try {
      data = await readFile(resolved);
    } catch {
      resolved = path.join(publicDir, "index.html");
      data = await readFile(resolved);
    }
    response.writeHead(200, { "content-type": contentTypes[path.extname(resolved)] || "application/octet-stream" });
    response.end(data);
  } catch (error) {
    sendJson(response, 500, { error: error.message });
  }
});

server.listen(port, "127.0.0.1", () => console.log(`sheet backend listening on ${port}`));
