import { createServer } from "node:http";
import { randomUUID } from "node:crypto";
import { mkdir, readFile, rename, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { executeComputeCommand, normalizeComputeState, verifyComputeState } from "./compute.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.resolve(here, "../frontend/dist");
const dataDir = path.join(here, "data");
const statePath = path.join(dataDir, "sheet-state.json");
const port = Number.parseInt(process.env.PORT || "3000", 10);
const host = process.env.HOST || "0.0.0.0";
let ready = false;
let state = { workbooks: [] };
let mutationQueue = Promise.resolve();

await mkdir(dataDir, { recursive: true });
try {
  const loaded = JSON.parse(await readFile(statePath, "utf8"));
  if (!loaded || !Array.isArray(loaded.workbooks)) throw new Error("state must contain a workbooks array");
  state = {
    ...loaded,
    workbooks: loaded.workbooks.map((workbook) => {
      const normalized = {
        ...normalizeComputeState(workbook),
        documentRevision: Math.max(0, Number(workbook.documentRevision) || 0),
      };
      const integrity = verifyComputeState(normalized.enterprise);
      if (!integrity.valid) {
        throw new Error(`workbook ${normalized.id || "unknown"} failed ${integrity.layer || integrity.reason} integrity`);
      }
      return normalized;
    }),
  };
} catch (error) {
  if (error?.code !== "ENOENT") {
    throw new Error(`Refusing to overwrite unreadable spreadsheet state at ${statePath}: ${error.message}`);
  }
  await persistSnapshot(state);
}
ready = true;

async function persistSnapshot(candidate) {
  const temporary = `${statePath}.${randomUUID()}.tmp`;
  try {
    await writeFile(temporary, JSON.stringify(candidate, null, 2), { mode: 0o600 });
    await rename(temporary, statePath);
  } finally {
    await unlink(temporary).catch(() => undefined);
  }
}

function serializeMutation(operation) {
  const queued = mutationQueue.then(operation, operation);
  mutationQueue = queued.then(() => undefined, () => undefined);
  return queued;
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
    documentRevision: 0,
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

function isRecord(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function validateWorkbookDocument(payload) {
  const name = String(payload.name || "").trim();
  if (!name || name.length > 160) throw new RequestError(422, "Workbook name must contain 1–160 characters");
  if (!Array.isArray(payload.sheets) || payload.sheets.length < 1 || payload.sheets.length > 100) {
    throw new RequestError(422, "Workbook must contain 1–100 worksheets");
  }
  const ids = new Set();
  const names = new Set();
  const sheets = payload.sheets.map((sheet) => {
    if (!isRecord(sheet) || !/^[A-Za-z0-9._:-]{1,128}$/.test(String(sheet.id || ""))) {
      throw new RequestError(422, "Worksheet id is invalid");
    }
    const sheetName = String(sheet.name || "").trim();
    if (!sheetName || sheetName.length > 100) throw new RequestError(422, "Worksheet name must contain 1–100 characters");
    if (ids.has(sheet.id) || names.has(sheetName.toLowerCase())) throw new RequestError(422, "Worksheet ids and names must be unique");
    ids.add(sheet.id);
    names.add(sheetName.toLowerCase());
    if (!isRecord(sheet.cells) || Object.keys(sheet.cells).length > 50_000) throw new RequestError(422, "Worksheet cells are invalid or exceed 50,000 entries");
    for (const [coordinate, value] of Object.entries(sheet.cells)) {
      if (!/^[A-Z]{1,3}[1-9]\d{0,5}$/.test(coordinate) || typeof value !== "string" || value.length > 65_536) {
        throw new RequestError(422, "Worksheet cell coordinate or value is invalid");
      }
    }
    if (!isRecord(sheet.validations || {})) throw new RequestError(422, "Worksheet validations must be an object");
    const selected = String(sheet.selected || "A1");
    const selection = Array.isArray(sheet.selection) ? sheet.selection.map(String) : [selected];
    if (!/^[A-Z]{1,3}[1-9]\d{0,5}$/.test(selected) || !selection.length || selection.length > 50_000 || selection.some((coordinate) => !/^[A-Z]{1,3}[1-9]\d{0,5}$/.test(coordinate))) {
      throw new RequestError(422, "Worksheet selection is invalid");
    }
    return { ...structuredClone(sheet), id: String(sheet.id), name: sheetName, selected, selection };
  });
  const activeSheetId = String(payload.activeSheetId || "");
  if (!ids.has(activeSheetId)) throw new RequestError(422, "Active worksheet must reference an existing worksheet");
  return { name, activeSheetId, sheets };
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
      const workbook = await serializeMutation(async () => {
        const candidate = structuredClone(state);
        const created = newWorkbook(String(payload.name || "Untitled workbook"), payload.cells || {});
        validateWorkbookDocument(created);
        candidate.workbooks.push(created);
        await persistSnapshot(candidate);
        state = candidate;
        return created;
      });
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
      const outcome = await serializeMutation(async () => {
        const workbook = findWorkbook(computeId);
        if (!workbook) return { status: 404, payload: { error: "Workbook not found" } };
        const mutating = !["compute.verify", "ledger.trial_balance"].includes(command.type);
        const expectedRevision = command.expectedRevision;
        if (mutating && !Number.isInteger(expectedRevision)) {
          return {
            status: 428,
            payload: {
              error: "Mutating compute commands require an integer expectedRevision",
              code: "revision_required",
              actualRevision: workbook.enterprise.revision,
            },
          };
        }
        if (expectedRevision !== undefined && expectedRevision !== workbook.enterprise.revision) {
          return {
            status: 409,
            payload: {
              error: "Enterprise state changed; refresh before retrying",
              code: "revision_conflict",
              expectedRevision,
              actualRevision: workbook.enterprise.revision,
            },
          };
        }
        const candidate = structuredClone(workbook);
        const result = executeComputeCommand(candidate, command, {
          actor: request.headers["x-langqi-user"] || "local-user",
        });
        if (result === null) return { status: 400, payload: { error: "Unknown compute command", code: "unknown_command" } };
        if (!result.ok) return { status: result.code === "integrity" ? 409 : 422, payload: { ...result, error: result.message } };
        const writesState = mutating && !result.replayed;
        const postIntegrity = verifyComputeState(candidate.enterprise);
        if (writesState && !postIntegrity.valid) {
          return {
            status: 409,
            payload: {
              ok: false,
              error: "Compute command produced an invalid enterprise state; transaction rolled back",
              code: "postcondition_failed",
              details: postIntegrity,
            },
          };
        }
        if (writesState) {
          candidate.enterprise.revision = workbook.enterprise.revision + 1;
          candidate.updatedAt = new Date().toISOString();
          const candidateState = structuredClone(state);
          candidateState.workbooks[state.workbooks.indexOf(workbook)] = candidate;
          await persistSnapshot(candidateState);
          state = candidateState;
        }
        const current = writesState ? candidate : workbook;
        return {
          status: 200,
          payload: {
            ...result,
            enterprise: current.enterprise,
            integrity: writesState ? postIntegrity : verifyComputeState(current.enterprise),
            updatedAt: current.updatedAt,
          },
        };
      });
      return sendJson(response, outcome.status, outcome.payload);
    }
    const workbook = matchWorkbook(url.pathname);
    if (workbook && request.method === "GET") {
      return sendJson(response, 200, workbook);
    }
    if (workbook && request.method === "PUT") {
      const payload = await body(request);
      const outcome = await serializeMutation(async () => {
        const current = findWorkbook(workbook.id);
        if (!current) return { status: 404, payload: { error: "Workbook not found" } };
        if (!Number.isInteger(payload.documentRevision)) {
          return { status: 428, payload: { error: "Workbook save requires documentRevision", code: "document_revision_required", actualRevision: current.documentRevision } };
        }
        if (payload.documentRevision !== current.documentRevision) {
          return { status: 409, payload: { error: "Workbook changed in another session", code: "document_revision_conflict", expectedRevision: payload.documentRevision, actualRevision: current.documentRevision } };
        }
        const document = validateWorkbookDocument(payload);
        const replacement = {
          ...current,
          ...document,
          id: current.id,
          createdAt: current.createdAt,
          updatedAt: new Date().toISOString(),
          documentRevision: current.documentRevision + 1,
          enterprise: current.enterprise,
        };
        normalizeComputeState(replacement);
        const candidateState = structuredClone(state);
        candidateState.workbooks[state.workbooks.indexOf(current)] = replacement;
        await persistSnapshot(candidateState);
        state = candidateState;
        return { status: 200, payload: replacement };
      });
      return sendJson(response, outcome.status, outcome.payload);
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

server.listen(port, host, () => console.log(`sheet backend listening on ${host}:${port}`));
