import { createServer } from "node:http";
import { randomUUID } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { executeComputeCommand, normalizeComputeState, verifyComputeState } from "./compute.mjs";

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
  if (!loaded || !Array.isArray(loaded.workbooks)) throw new Error("state must contain a workbooks array");
  state = { ...loaded, workbooks: loaded.workbooks.map((workbook) => normalizeComputeState(workbook)) };
} catch (error) {
  if (error?.code !== "ENOENT") {
    throw new Error(`Refusing to overwrite unreadable spreadsheet state at ${statePath}: ${error.message}`);
  }
  await writeFile(statePath, JSON.stringify(state, null, 2), { flag: "wx" });
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

class RequestError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function body(request) {
  const maximumBytes = 1_048_576;
  const declaredLength = Number(request.headers["content-length"] || 0);
  if (Number.isFinite(declaredLength) && declaredLength > maximumBytes) throw new RequestError(413, "Request body exceeds 1 MiB");
  const chunks = [];
  let total = 0;
  for await (const chunk of request) {
    total += chunk.length;
    if (total > maximumBytes) throw new RequestError(413, "Request body exceeds 1 MiB");
    chunks.push(chunk);
  }
  if (!chunks.length) return {};
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    throw new RequestError(400, "Request body must be valid JSON");
  }
}

function newWorkbook(name = "Untitled workbook", cells = {}) {
  const now = new Date().toISOString();
  return normalizeComputeState({
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
  });
}

function matchWorkbook(pathname) {
  const match = /^\/api\/workbooks\/([^/]+)$/.exec(pathname);
  if (!match) return null;
  return state.workbooks.find((item) => item.id === decodeURIComponent(match[1])) || null;
}

function computeWorkbookId(pathname) {
  const match = /^\/api\/workbooks\/([^/]+)\/compute$/.exec(pathname);
  return match ? decodeURIComponent(match[1]) : null;
}

function findWorkbook(id) {
  return state.workbooks.find((item) => item.id === id) || null;
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
    const computeId = computeWorkbookId(url.pathname);
    if (computeId && request.method === "GET") {
      const workbook = findWorkbook(computeId);
      if (!workbook) return sendJson(response, 404, { error: "Workbook not found" });
      return sendJson(response, 200, {
        enterprise: workbook.enterprise,
        integrity: verifyComputeState(workbook.enterprise),
        updatedAt: workbook.updatedAt,
      });
    }
    if (computeId && request.method === "POST") {
      const command = await body(request);
      const workbook = findWorkbook(computeId);
      if (!workbook) return sendJson(response, 404, { error: "Workbook not found" });
      const mutating = !["compute.verify", "ledger.trial_balance"].includes(command.type);
      const expectedRevision = command.expectedRevision;
      if (mutating && !Number.isInteger(expectedRevision)) {
        return sendJson(response, 428, {
          error: "Mutating compute commands require an integer expectedRevision",
          code: "revision_required",
          actualRevision: workbook.enterprise.revision,
        });
      }
      if (expectedRevision !== undefined && expectedRevision !== workbook.enterprise.revision) {
        return sendJson(response, 409, {
          error: "Enterprise state changed; refresh before retrying",
          code: "revision_conflict",
          expectedRevision,
          actualRevision: workbook.enterprise.revision,
        });
      }
      const candidate = structuredClone(workbook);
      const result = executeComputeCommand(candidate, command, {
        actor: request.headers["x-langqi-user"] || "local-user",
      });
      if (result === null) return sendJson(response, 400, { error: "Unknown compute command", code: "unknown_command" });
      if (!result.ok) return sendJson(response, result.code === "integrity" ? 409 : 422, { ...result, error: result.message });
      const writesState = mutating && !result.replayed;
      const postIntegrity = verifyComputeState(candidate.enterprise);
      if (writesState && !postIntegrity.valid) {
        return sendJson(response, 409, {
          ok: false,
          error: "Compute command produced an invalid enterprise state; transaction rolled back",
          code: "postcondition_failed",
          details: postIntegrity,
        });
      }
      if (writesState) {
        candidate.enterprise.revision = workbook.enterprise.revision + 1;
        candidate.updatedAt = new Date().toISOString();
        state.workbooks[state.workbooks.indexOf(workbook)] = candidate;
        await persist();
      }
      const current = writesState ? candidate : workbook;
      return sendJson(response, 200, {
        ...result,
        enterprise: current.enterprise,
        integrity: writesState ? postIntegrity : verifyComputeState(current.enterprise),
        updatedAt: current.updatedAt,
      });
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
        enterprise: workbook.enterprise,
      };
      normalizeComputeState(replacement);
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
    sendJson(response, error.status || 500, { error: error.message });
  }
});

server.listen(port, "127.0.0.1", () => console.log(`sheet backend listening on ${port}`));
