import { createServer } from "node:http";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";

const port = Number(process.env.PORT || 3000);
const host = process.env.HOST || "127.0.0.1";
const dataPath = path.join(process.env.DATA_DIR || path.join(process.cwd(), "data"), "state.json");
const publicDir = path.resolve(process.cwd(), "../frontend/dist");
const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8" };
const ROWS = 30;
const COLS = 12;

function colName(index) {
  let n = index + 1;
  let name = "";
  while (n > 0) {
    const rem = (n - 1) % 26;
    name = String.fromCharCode(65 + rem) + name;
    n = Math.floor((n - 1) / 26);
  }
  return name;
}

function colIndex(name) {
  let n = 0;
  for (const ch of name) n = n * 26 + (ch.charCodeAt(0) - 64);
  return n - 1;
}

function addr(col, row) {
  return `${colName(col)}${row}`;
}

function parseAddr(value) {
  const match = /^([A-Z]+)([1-9][0-9]*)$/.exec(String(value || "").toUpperCase());
  if (!match) return null;
  return { col: colIndex(match[1]), row: Number(match[2]), key: `${match[1]}${match[2]}` };
}

function blankSheet(name) {
  return { name, cells: {}, selection: "A1" };
}

function seedState() {
  return {
    workbooks: [{
      id: "q3-sales",
      name: "Q3 Sales",
      updated: "2 hours ago",
      active: "Sheet1",
      undo: [],
      redo: [],
      sheets: [{
        name: "Sheet1",
        selection: "A1",
        cells: {
          A1: "Region",
          B1: "Sales",
          C1: "Status",
          A2: "East",
          B2: "1200",
          C2: "Open",
          A3: "North",
          B3: "800",
          C3: "Closed",
          A4: "South",
          B4: "700",
          C4: "Open",
        },
      }],
    }],
  };
}

let writeChain = Promise.resolve();

async function loadState() {
  try {
    const parsed = JSON.parse(await readFile(dataPath, "utf8"));
    if (!parsed.workbooks) return seedState();
    return parsed;
  } catch (error) {
    if (error && error.code === "ENOENT") return seedState();
    throw error;
  }
}

async function saveState(next) {
  await mkdir(path.dirname(dataPath), { recursive: true });
  const temporary = `${dataPath}.${randomUUID()}.tmp`;
  await writeFile(temporary, JSON.stringify(next));
  await rename(temporary, dataPath);
  return next;
}

function transact(mutator) {
  const run = writeChain.then(async () => {
    const draft = structuredClone(await loadState());
    const result = await mutator(draft);
    await saveState(draft);
    return result;
  });
  writeChain = run.then(() => undefined, () => undefined);
  return run;
}

function sendJson(response, status, body, extraHeaders) {
  response.writeHead(status, { "content-type": "application/json; charset=utf-8", ...(extraHeaders || {}) });
  response.end(JSON.stringify(body));
}

function readBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => {
      if (!chunks.length) { resolve({}); return; }
      try { resolve(JSON.parse(Buffer.concat(chunks).toString("utf8"))); }
      catch { reject(Object.assign(new Error("Invalid JSON"), { status: 400 })); }
    });
    request.on("error", reject);
  });
}

function findBook(state, id) {
  return state.workbooks.find((item) => item.id === id) || null;
}

function activeSheet(book) {
  return book.sheets.find((item) => item.name === book.active) || book.sheets[0];
}

function cellRaw(sheet, key) {
  return sheet.cells[key] ?? "";
}

function displayValue(sheet, key, stack = new Set()) {
  const raw = String(cellRaw(sheet, key));
  if (!raw.startsWith("=")) return raw;
  if (stack.has(key)) return "#REF!";
  stack.add(key);
  const result = evaluate(sheet, raw.slice(1), stack);
  stack.delete(key);
  return result;
}

function evaluate(sheet, expr, stack) {
  let index = 0;
  const source = expr.trim();
  if (source.startsWith("#")) return source;
  function peek() { return source[index] || ""; }
  function skip() { while (peek() === " ") index += 1; }
  function parseExpr() {
    let value = parseTerm();
    skip();
    while (peek() === "+" || peek() === "-") {
      const op = peek();
      index += 1;
      const right = parseTerm();
      if (typeof value === "string" || typeof right === "string") return "#ERROR!";
      value = op === "+" ? value + right : value - right;
    }
    return value;
  }
  function parseTerm() {
    let value = parseUnary();
    skip();
    while (peek() === "*" || peek() === "/") {
      const op = peek();
      index += 1;
      const right = parseUnary();
      if (typeof value === "string" || typeof right === "string") return "#ERROR!";
      if (op === "/" && right === 0) return "#DIV/0!";
      value = op === "*" ? value * right : value / right;
    }
    return value;
  }
  function parseUnary() {
    skip();
    if (peek() === "+") { index += 1; return parseUnary(); }
    if (peek() === "-") { index += 1; const value = parseUnary(); return typeof value === "number" ? -value : value; }
    return parsePrimary();
  }
  function parsePrimary() {
    skip();
    if (peek() === "(") {
      index += 1;
      const value = parseExpr();
      skip();
      if (peek() === ")") index += 1;
      return value;
    }
    if (/[0-9.]/.test(peek())) {
      const start = index;
      while (/[0-9.]/.test(peek())) index += 1;
      return Number(source.slice(start, index));
    }
    if (peek() === "$" || /[A-Za-z]/.test(peek())) {
      if (peek() === "$") index += 1;
      if (!/[A-Za-z]/.test(peek())) return "#ERROR!";
      const start = index;
      while (/[A-Za-z]/.test(peek())) index += 1;
      const word = source.slice(start, index).toUpperCase();
      skip();
      if (peek() === "(") {
        index += 1;
        const args = [];
        skip();
        if (peek() !== ")") {
          args.push(parseArg());
          skip();
          while (peek() === ",") { index += 1; args.push(parseArg()); skip(); }
        }
        skip();
        if (peek() === ")") index += 1;
        return callFn(word, args.flat());
      }
      if (peek() === "$") index += 1;
      const rest = source.slice(index);
      const ref = /^([0-9]+)/.exec(rest);
      if (!ref) return "#NAME?";
      index += ref[0].length;
      const key = `${word}${ref[1]}`;
      if (!parseAddr(key)) return "#REF!";
      const shown = displayValue(sheet, key, stack);
      if (typeof shown === "string" && shown.startsWith("#")) return shown;
      const num = Number(shown);
      return shown === "" || Number.isNaN(num) ? 0 : num;
    }
    return "#ERROR!";
  }
  function parseArg() {
    skip();
    const range = /^\$?([A-Z]+)\$?([0-9]+)\s*:\s*\$?([A-Z]+)\$?([0-9]+)/i.exec(source.slice(index));
    if (range) {
      index += range[0].length;
      const c1 = colIndex(range[1].toUpperCase());
      const r1 = Number(range[2]);
      const c2 = colIndex(range[3].toUpperCase());
      const r2 = Number(range[4]);
      const values = [];
      for (let row = Math.min(r1, r2); row <= Math.max(r1, r2); row += 1) {
        for (let col = Math.min(c1, c2); col <= Math.max(c1, c2); col += 1) {
          values.push(displayValue(sheet, addr(col, row), stack));
        }
      }
      return values;
    }
    return [parseExpr()];
  }
  function callFn(name, values) {
    const known = ["SUM", "AVERAGE", "COUNT", "MIN", "MAX"];
    if (!known.includes(name)) return "#NAME?";
    const numbers = values.filter((item) => item !== "" && !Number.isNaN(Number(item)) && !String(item).startsWith("#")).map(Number);
    if (name === "COUNT") return numbers.length;
    if (!numbers.length) return 0;
    if (name === "SUM") return numbers.reduce((sum, item) => sum + item, 0);
    if (name === "AVERAGE") return numbers.reduce((sum, item) => sum + item, 0) / numbers.length;
    if (name === "MIN") return Math.min(...numbers);
    return Math.max(...numbers);
  }
  try {
    const value = parseExpr();
    if (typeof value === "number" && !Number.isFinite(value)) return "#ERROR!";
    return typeof value === "number" ? String(value) : value;
  } catch {
    return "#ERROR!";
  }
}

function touch(book) {
  book.updated = "just now";
}

function snapshot(book) {
  book.undo.push(JSON.stringify({ sheets: book.sheets, active: book.active, name: book.name }));
  if (book.undo.length > 30) book.undo.shift();
  book.redo = [];
}

function conditionMatches(shown, rule) {
  const op = rule.condition || "";
  const expected = rule.value || "";
  if (op === "Is empty") return shown === "";
  if (op === "Is not empty") return shown !== "";
  if (!expected) return true;
  if (op === "Text contains") return shown.toLowerCase().includes(expected.toLowerCase());
  if (op === "Greater than") return Number(shown) > Number(expected);
  if (op === "Before") {
    const left = Date.parse(shown);
    const right = Date.parse(expected);
    return Number.isFinite(left) && Number.isFinite(right) && left < right;
  }
  return true;
}

function rowVisible(sheet, row) {
  const filters = sheet.filters || {};
  const columns = Object.keys(filters);
  if (!columns.length || row === 1) return true;
  const hasRecord = columns.some((column) => String(cellRaw(sheet, `${column}${row}`)) !== "");
  if (!hasRecord) return true;
  return columns.every((column) => {
    const rule = filters[column];
    const shown = String(displayValue(sheet, `${column}${row}`));
    if (Array.isArray(rule.include) && !rule.include.includes(shown)) return false;
    return conditionMatches(shown, rule);
  });
}

function sheetGrid(sheet) {
  const rows = [];
  for (let row = 1; row <= ROWS; row += 1) {
    const cells = [];
    for (let col = 0; col < COLS; col += 1) {
      const key = addr(col, row);
      cells.push({ addr: key, raw: String(cellRaw(sheet, key)), value: String(displayValue(sheet, key)) });
    }
    rows.push({ row, cells, hidden: !rowVisible(sheet, row) });
  }
  return rows;
}

function bookView(book) {
  const sheet = activeSheet(book);
  return {
    id: book.id,
    name: book.name,
    updated: book.updated,
    active: sheet.name,
    selection: sheet.selection || "A1",
    selectionAnchor: sheet.anchor || sheet.selection || "A1",
    selectionFocus: sheet.focus || sheet.selection || "A1",
    sheets: book.sheets.map((item) => item.name),
    grid: sheetGrid(sheet),
    columns: Array.from({ length: COLS }, (_, index) => colName(index)),
    validation: sheet.validation || null,
    sourceRange: usedRange(sheet),
    pivot: sheet.pivot || null,
    pivotHeaders: pivotHeaders(book, sheet),
    canUndo: Array.isArray(book.undo) && book.undo.length > 0,
    canRedo: Array.isArray(book.redo) && book.redo.length > 0,
  };
}

function adjustFormula(formula, axis, target, delta) {
  if (!String(formula).startsWith("=")) return formula;
  let broken = false;
  const next = formula.replace(/(\$?)([A-Za-z]+)(\$?)([0-9]+)/g, (full, absCol, col, absRow, rowText) => {
    if (!/^[A-Z]+$/i.test(col)) return full;
    let colN = colIndex(col);
    let rowN = Number(rowText);
    const move = (locked, value) => {
      if (locked) return value;
      if (delta > 0 && value >= target) return value + delta;
      if (delta < 0 && value === target) return null;
      if (delta < 0 && value > target) return value - 1;
      return value;
    };
    if (axis === "row") {
      const moved = move(Boolean(absRow), rowN);
      if (moved == null) { broken = true; return "#REF!"; }
      rowN = moved;
    } else {
      const moved = move(Boolean(absCol), colN);
      if (moved == null) { broken = true; return "#REF!"; }
      colN = moved;
    }
    if (colN < 0 || colN >= COLS || rowN < 1 || rowN > ROWS) { broken = true; return "#REF!"; }
    return `${absCol}${colName(colN)}${absRow}${rowN}`;
  });
  return broken ? "=#REF!" : next;
}

function numberRangeError(rule) {
  if (Number(rule.minimum) === 0 && Number(rule.maximum) === 100) return "Please enter a number from 0 to 100";
  return `Please enter a number between ${rule.minimum} and ${rule.maximum}`;
}

function ruleCovers(rule, key) {
  if (!rule) return false;
  const here = parseAddr(key);
  const start = parseAddr(rule.start || rule.cell || "");
  const end = parseAddr(rule.end || rule.start || rule.cell || "");
  if (!here || !start || !end) return false;
  return here.col >= Math.min(start.col, end.col) && here.col <= Math.max(start.col, end.col)
    && here.row >= Math.min(start.row, end.row) && here.row <= Math.max(start.row, end.row);
}

function parseRange(value) {
  const match = /^([A-Z]+)([0-9]+):([A-Z]+)([0-9]+)$/i.exec(String(value || ""));
  if (!match) return null;
  const c1 = colIndex(match[1].toUpperCase());
  const r1 = Number(match[2]);
  const c2 = colIndex(match[3].toUpperCase());
  const r2 = Number(match[4]);
  return { c1: Math.min(c1, c2), r1: Math.min(r1, r2), c2: Math.max(c1, c2), r2: Math.max(r1, r2) };
}

function pivotHeaders(book, sheet) {
  if (!sheet.pivot) return [];
  const source = book.sheets.find((item) => item.name === sheet.pivot.source);
  const range = source && parseRange(sheet.pivot.range);
  if (!source || !range) return [];
  const headers = [];
  for (let col = range.c1; col <= range.c2; col += 1) {
    const name = String(displayValue(source, addr(col, range.r1)));
    if (name) headers.push(name);
  }
  return headers;
}

function shiftFormula(formula, dCol, dRow) {
  if (!String(formula).startsWith("=")) return formula;
  let broken = false;
  const next = formula.replace(/(\$?)([A-Za-z]+)(\$?)([0-9]+)/g, (full, absCol, col, absRow, row) => {
    if (!/^[A-Z]+$/i.test(col)) return full;
    let nextCol = col.toUpperCase();
    let nextRow = Number(row);
    if (!absCol) {
      const index = colIndex(nextCol) + dCol;
      if (index < 0 || index >= COLS) { broken = true; return "#REF!"; }
      nextCol = colName(index);
    }
    if (!absRow) {
      nextRow += dRow;
      if (nextRow < 1 || nextRow > ROWS) { broken = true; return "#REF!"; }
    }
    return `${absCol}${nextCol}${absRow}${nextRow}`;
  });
  return broken ? "=#REF!" : next;
}

function pivotRecords(book, config) {
  const source = book.sheets.find((item) => item.name === config.source);
  const range = source && parseRange(config.range);
  if (!source || !range) return { error: "Pivot field is no longer available. Select a new field." };
  const headers = [];
  for (let col = range.c1; col <= range.c2; col += 1) {
    headers.push({ name: String(displayValue(source, addr(col, range.r1))), col });
  }
  const find = (name) => headers.find((item) => item.name === name);
  const rowField = find(config.rows);
  const valueField = find(config.values);
  const columnField = config.columns ? find(config.columns) : null;
  if (!rowField || !valueField || (config.columns && !columnField)) {
    return { error: "Pivot field is no longer available. Select a new field." };
  }
  const records = [];
  for (let row = range.r1 + 1; row <= range.r2; row += 1) {
    const value = String(displayValue(source, addr(valueField.col, row)));
    records.push({
      row: String(displayValue(source, addr(rowField.col, row))),
      column: columnField ? String(displayValue(source, addr(columnField.col, row))) : "",
      value,
    });
  }
  return { records, rowField, valueField, columnField };
}

function aggregate(method, records) {
  if (method === "COUNT") return String(records.filter((item) => item.value !== "").length);
  const numbers = records
    .map((item) => item.value)
    .filter((item) => item !== "" && !Number.isNaN(Number(item)))
    .map(Number);
  if (!numbers.length) return null;
  if (method === "AVERAGE") return String(numbers.reduce((sum, item) => sum + item, 0) / numbers.length);
  return String(numbers.reduce((sum, item) => sum + item, 0));
}

function uniqueOrder(records, key) {
  const seen = [];
  for (const record of records) {
    if (!seen.includes(record[key])) seen.push(record[key]);
  }
  return seen;
}

function buildPivot(book, sheet) {
  const config = sheet.pivot;
  const loaded = pivotRecords(book, config);
  if (loaded.error) return loaded;
  const method = config.summarize || "SUM";
  if (method !== "COUNT" && aggregate(method, loaded.records) === null) {
    return { error: "Value field requires numeric values" };
  }
  const cells = {};
  const rowKeys = uniqueOrder(loaded.records, "row");
  if (!config.columns) {
    cells.A1 = config.rows;
    cells.B1 = `${method} of ${config.values}`;
    rowKeys.forEach((key, index) => {
      const matched = loaded.records.filter((item) => item.row === key);
      cells[addr(0, index + 2)] = key;
      cells[addr(1, index + 2)] = aggregate(method, matched) || "0";
    });
    cells[addr(0, rowKeys.length + 2)] = "Grand Total";
    cells[addr(1, rowKeys.length + 2)] = aggregate(method, loaded.records) || "0";
    return { cells };
  }
  const columnKeys = uniqueOrder(loaded.records, "column");
  cells.A1 = config.rows;
  columnKeys.forEach((key, index) => { cells[addr(index + 1, 1)] = key; });
  cells[addr(columnKeys.length + 1, 1)] = "Grand Total";
  rowKeys.forEach((rowKey, rowIndex) => {
    cells[addr(0, rowIndex + 2)] = rowKey;
    columnKeys.forEach((columnKey, columnIndex) => {
      const matched = loaded.records.filter((item) => item.row === rowKey && item.column === columnKey);
      cells[addr(columnIndex + 1, rowIndex + 2)] = aggregate(method, matched) || "0";
    });
    const rowMatched = loaded.records.filter((item) => item.row === rowKey);
    cells[addr(columnKeys.length + 1, rowIndex + 2)] = aggregate(method, rowMatched) || "0";
  });
  const totalRow = rowKeys.length + 2;
  cells[addr(0, totalRow)] = "Grand Total";
  columnKeys.forEach((columnKey, columnIndex) => {
    const matched = loaded.records.filter((item) => item.column === columnKey);
    cells[addr(columnIndex + 1, totalRow)] = aggregate(method, matched) || "0";
  });
  cells[addr(columnKeys.length + 1, totalRow)] = aggregate(method, loaded.records) || "0";
  return { cells };
}

function usedRange(sheet) {
  let maxRow = 1;
  let maxCol = 0;
  let minRow = ROWS;
  let minCol = COLS;
  let any = false;
  for (const key of Object.keys(sheet.cells)) {
    const parsed = parseAddr(key);
    if (!parsed) continue;
    any = true;
    maxRow = Math.max(maxRow, parsed.row);
    maxCol = Math.max(maxCol, parsed.col);
    minRow = Math.min(minRow, parsed.row);
    minCol = Math.min(minCol, parsed.col);
  }
  if (!any) return "A1";
  return `${addr(minCol, minRow)}:${addr(maxCol, maxRow)}`;
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') { field += '"'; i += 1; }
        else quoted = false;
      } else field += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") { row.push(field); field = ""; }
    else if (ch === "\n") { row.push(field); rows.push(row); row = []; field = ""; }
    else if (ch !== "\r") field += ch;
  }
  if (quoted) return null;
  if (field.length || row.length) { row.push(field); rows.push(row); }
  return rows;
}

function csvEscape(value) {
  const text = String(value ?? "");
  if (/[",\n]/.test(text)) return `"${text.replaceAll('"', '""')}"`;
  return text;
}

function usedCsv(sheet) {
  let maxRow = 1;
  let maxCol = 0;
  for (const key of Object.keys(sheet.cells)) {
    const parsed = parseAddr(key);
    if (!parsed) continue;
    maxRow = Math.max(maxRow, parsed.row);
    maxCol = Math.max(maxCol, parsed.col);
  }
  const lines = [];
  for (let row = 1; row <= maxRow; row += 1) {
    const fields = [];
    for (let col = 0; col <= maxCol; col += 1) fields.push(csvEscape(displayValue(sheet, addr(col, row))));
    lines.push(fields.join(","));
  }
  return lines.join("\n");
}

function shiftPivotRanges(book, sourceName, axis, target, delta) {
  book.sheets.forEach((item) => {
    if (!item.pivot || item.pivot.source !== sourceName) return;
    const range = parseRange(item.pivot.range);
    if (!range) return;
    if (axis === "row") {
      const r1 = moveBounded(range.r1, target, delta, 1, ROWS);
      const r2 = moveBounded(range.r2, target, delta, 1, ROWS);
      if (r1 == null || r2 == null) return;
      item.pivot.range = `${colName(range.c1)}${r1}:${colName(range.c2)}${r2}`;
    } else {
      const c1 = moveBounded(range.c1, target, delta, 1, COLS);
      const c2 = moveBounded(range.c2, target, delta, 1, COLS);
      if (c1 == null || c2 == null) return;
      item.pivot.range = `${colName(c1)}${range.r1}:${colName(c2)}${range.r2}`;
    }
  });
}

function moveBounded(value, target, delta, min, max) {
  let next = value;
  if (delta > 0 && value >= target) next = value + delta;
  else if (delta < 0 && value === target) return null;
  else if (delta < 0 && value > target) next = value - 1;
  if (next < min || next > max) return null;
  return next;
}

function shiftValidation(sheet, axis, target, delta) {
  const rule = sheet.validation;
  if (!rule) return;
  const start = parseAddr(rule.start || rule.cell || "");
  const end = parseAddr(rule.end || rule.start || rule.cell || "");
  if (!start || !end) return;
  if (axis === "row") {
    const r1 = moveBounded(start.row, target, delta, 1, ROWS);
    const r2 = moveBounded(end.row, target, delta, 1, ROWS);
    if (r1 == null || r2 == null) {
      delete sheet.validation;
      return;
    }
    rule.start = addr(start.col, r1);
    rule.end = addr(end.col, r2);
  } else {
    const c1 = moveBounded(start.col, target, delta, 0, COLS - 1);
    const c2 = moveBounded(end.col, target, delta, 0, COLS - 1);
    if (c1 == null || c2 == null) {
      delete sheet.validation;
      return;
    }
    rule.start = addr(c1, start.row);
    rule.end = addr(c2, end.row);
  }
  rule.cell = rule.start;
}

function shiftFilters(sheet, target, delta) {
  if (!sheet.filters) return;
  const next = {};
  Object.entries(sheet.filters).forEach(([letter, rule]) => {
    const moved = moveBounded(colIndex(letter), target, delta, 0, COLS - 1);
    if (moved != null) next[colName(moved)] = rule;
  });
  sheet.filters = next;
}

function shiftRow(sheet, target, delta) {
  for (const key of Object.keys(sheet.cells)) sheet.cells[key] = adjustFormula(sheet.cells[key], "row", target, delta);
  const next = {};
  for (const [key, raw] of Object.entries(sheet.cells)) {
    const parsed = parseAddr(key);
    if (!parsed) continue;
    let row = parsed.row;
    if (delta > 0 && row >= target) row += delta;
    if (delta < 0 && row === target) continue;
    if (delta < 0 && row > target) row -= 1;
    next[addr(parsed.col, row)] = raw;
  }
  sheet.cells = next;
  shiftValidation(sheet, "row", target, delta);
}

function shiftCol(sheet, target, delta) {
  for (const key of Object.keys(sheet.cells)) sheet.cells[key] = adjustFormula(sheet.cells[key], "col", target, delta);
  const next = {};
  for (const [key, raw] of Object.entries(sheet.cells)) {
    const parsed = parseAddr(key);
    if (!parsed) continue;
    let col = parsed.col;
    if (delta > 0 && col >= target) col += delta;
    if (delta < 0 && col === target) continue;
    if (delta < 0 && col > target) col -= 1;
    next[addr(col, parsed.row)] = raw;
  }
  sheet.cells = next;
  shiftValidation(sheet, "col", target, delta);
  shiftFilters(sheet, target, delta);
}

async function handleApi(request, response, url) {
  const parts = url.pathname.split("/").filter(Boolean);
  if (request.method === "GET" && url.pathname === "/api/health") {
    sendJson(response, 200, { ready: true });
    return true;
  }
  if (request.method === "GET" && url.pathname === "/api/workbooks") {
    const state = await loadState();
    sendJson(response, 200, { workbooks: state.workbooks.map((item) => ({ id: item.id, name: item.name, updated: item.updated })) });
    return true;
  }
  if (request.method === "POST" && url.pathname === "/api/workbooks") {
    const created = await transact((draft) => {
      const id = randomUUID().slice(0, 8);
      const used = new Set(draft.workbooks.map((item) => item.name));
      let name = "Blank workbook";
      let n = 2;
      while (used.has(name)) { name = `Blank workbook ${n}`; n += 1; }
      draft.workbooks.push({ id, name, updated: "just now", active: "Sheet1", undo: [], redo: [], sheets: [blankSheet("Sheet1")] });
      return id;
    });
    sendJson(response, 200, { ok: true, id: created });
    return true;
  }
  if (request.method === "POST" && url.pathname === "/api/workbooks/import") {
    const body = await readBody(request);
    const imported = await transact((draft) => {
      const rows = parseCsv(String(body.csv || ""));
      if (!rows) return { status: 400, error: "Invalid CSV file format. Import failed." };
      const sheet = blankSheet("Sheet1");
      rows.forEach((fields, rowIndex) => {
        fields.forEach((field, colIndex) => {
          if (field !== "") sheet.cells[addr(colIndex, rowIndex + 1)] = field;
        });
      });
      const id = randomUUID().slice(0, 8);
      draft.workbooks.push({
        id,
        name: String(body.name || "Imported workbook"),
        updated: "just now",
        active: "Sheet1",
        undo: [],
        redo: [],
        sheets: [sheet],
      });
      return { status: 200, id };
    });
    sendJson(response, imported.status, imported.status === 200 ? { ok: true, id: imported.id } : { error: imported.error });
    return true;
  }
  if (parts[0] === "api" && parts[1] === "workbooks" && parts[2]) {
    const id = decodeURIComponent(parts[2]);
    const action = parts[3] || "";
    if (request.method === "GET" && !action) {
      const state = await loadState();
      const book = findBook(state, id);
      if (!book) { sendJson(response, 404, { error: "Not found" }); return true; }
      sendJson(response, 200, bookView(book));
      return true;
    }
    if (request.method === "GET" && action === "export.csv") {
      const state = await loadState();
      const book = findBook(state, id);
      if (!book) { sendJson(response, 404, { error: "Not found" }); return true; }
      const body = usedCsv(activeSheet(book));
      response.writeHead(200, {
        "content-type": "text/csv; charset=utf-8",
        "content-disposition": `attachment; filename="${book.name}.csv"`,
      });
      response.end(body);
      return true;
    }
    if (request.method === "POST") {
      const body = await readBody(request);
      const updated = await transact((draft) => {
        const book = findBook(draft, id);
        if (!book) return { status: 404, error: "Not found" };
        const sheet = activeSheet(book);
        if (action === "rename") {
          const name = String(body.name || "").trim();
          if (!name) return { status: 400, error: "Workbook name cannot be empty" };
          snapshot(book);
          book.name = name;
          touch(book);
          return { status: 200 };
        }
        if (action === "select") {
          const target = book.sheets.find((item) => item.name === body.sheet) || sheet;
          book.active = target.name;
          if (parseAddr(body.cell)) target.selection = String(body.cell).toUpperCase();
          if (parseAddr(body.anchor)) target.anchor = String(body.anchor).toUpperCase();
          if (parseAddr(body.focus || body.cell)) target.focus = String(body.focus || body.cell).toUpperCase();
          if (!target.anchor) target.anchor = target.selection || "A1";
          if (!target.focus) target.focus = target.selection || "A1";
          return { status: 200 };
        }
        if (action === "cell") {
          const key = String(body.cell || sheet.selection || "A1").toUpperCase();
          if (!parseAddr(key)) return { status: 400, error: "#REF!" };
          const value = String(body.value ?? "");
          const rule = sheet.validation;
          if (ruleCovers(rule, key) && rule.type === "Number range" && value !== "" && !value.startsWith("=")) {
            const number = Number(value);
            const minimum = Number(rule.minimum);
            const maximum = Number(rule.maximum);
            if (!Number.isFinite(number) || number < minimum || number > maximum) {
              return { status: 400, error: numberRangeError(rule) };
            }
          }
          if (ruleCovers(rule, key) && rule.type === "Dropdown" && value !== "" && !value.startsWith("=")) {
            const allowed = String(rule.values || "").split(",").map((item) => item.trim()).filter(Boolean);
            if (allowed.length && !allowed.includes(value.trim())) {
              return { status: 400, error: `Please select one of the following values: ${allowed.join(", ")}` };
            }
          }
          snapshot(book);
          sheet.cells[key] = String(body.value ?? "");
          sheet.selection = key;
          touch(book);
          return { status: 200 };
        }
        if (action === "add-sheet" || action === "pivot") {
          snapshot(book);
          const prefix = action === "pivot" ? "Pivot" : "Sheet";
          let n = 1;
          const names = new Set(book.sheets.map((item) => item.name));
          while (names.has(`${prefix}${n}`)) n += 1;
          const name = `${prefix}${n}`;
          const created = blankSheet(name);
          if (action === "pivot") {
            created.pivot = {
              source: sheet.name,
              range: usedRange(sheet),
              rows: "",
              columns: "",
              values: "",
              summarize: "SUM",
            };
          }
          book.sheets.push(created);
          book.active = name;
          touch(book);
          return { status: 200, name };
        }
        if (action === "activate-sheet") {
          if (!book.sheets.some((item) => item.name === body.name)) return { status: 404, error: "Not found" };
          book.active = body.name;
          return { status: 200 };
        }
        if (action === "rename-sheet") {
          const name = String(body.name || "").trim();
          if (!name) return { status: 400, error: "Worksheet name cannot be empty" };
          if (book.sheets.some((item) => item.name === name && item !== sheet)) return { status: 400, error: "Worksheet name already exists" };
          snapshot(book);
          sheet.name = name;
          book.active = name;
          touch(book);
          return { status: 200 };
        }
        if (action === "delete-sheet") {
          if (book.sheets.length < 2) return { status: 400, error: "A workbook must contain at least one worksheet" };
          if (book.sheets.some((item) => item.pivot && item.pivot.source === sheet.name)) {
            return { status: 400, error: "Please delete or rebuild dependent pivot tables first" };
          }
          snapshot(book);
          const index = book.sheets.findIndex((item) => item.name === sheet.name);
          book.sheets.splice(index, 1);
          book.active = book.sheets[Math.max(0, index - 1)].name;
          touch(book);
          return { status: 200 };
        }
        if (action === "row") {
          const parsed = parseAddr(sheet.selection || "A1");
          const row = Number(body.row || parsed.row);
          snapshot(book);
          if (body.op === "above") { shiftRow(sheet, row, 1); shiftPivotRanges(book, sheet.name, "row", row, 1); }
          if (body.op === "below") { shiftRow(sheet, row + 1, 1); shiftPivotRanges(book, sheet.name, "row", row + 1, 1); }
          if (body.op === "delete") { shiftRow(sheet, row, -1); shiftPivotRanges(book, sheet.name, "row", row, -1); }
          touch(book);
          return { status: 200 };
        }
        if (action === "column") {
          const parsed = parseAddr(sheet.selection || "A1");
          const col = body.col ? colIndex(String(body.col).toUpperCase()) : parsed.col;
          snapshot(book);
          if (body.op === "left") { shiftCol(sheet, col, 1); shiftPivotRanges(book, sheet.name, "col", col, 1); }
          if (body.op === "right") { shiftCol(sheet, col + 1, 1); shiftPivotRanges(book, sheet.name, "col", col + 1, 1); }
          if (body.op === "delete") { shiftCol(sheet, col, -1); shiftPivotRanges(book, sheet.name, "col", col, -1); }
          touch(book);
          return { status: 200 };
        }
        if (action === "paste") {
          const start = parseAddr(body.cell || sheet.selection || "A1");
          const origin = parseAddr(body.from || body.cell || sheet.selection || "A1");
          const rows = String(body.text || "").replace(/\r/g, "").split("\n").filter((line, index, all) => line !== "" || index < all.length - 1);
          const rule = sheet.validation;
          const writes = [];
          for (let rowOffset = 0; rowOffset < rows.length; rowOffset += 1) {
            const fields = rows[rowOffset].split("\t");
            for (let colOffset = 0; colOffset < fields.length; colOffset += 1) {
              let field = fields[colOffset];
              if (field.startsWith("=")) field = shiftFormula(field, start.col - origin.col, start.row - origin.row);
              if (ruleCovers(rule, addr(start.col + colOffset, start.row + rowOffset)) && rule.type === "Number range" && field !== "" && !field.startsWith("=")) {
                const number = Number(field);
                if (!Number.isFinite(number) || number < Number(rule.minimum) || number > Number(rule.maximum)) {
                  return { status: 400, error: numberRangeError(rule) };
                }
              }
              writes.push([addr(start.col + colOffset, start.row + rowOffset), field]);
            }
          }
          snapshot(book);
          writes.forEach(([key, field]) => { sheet.cells[key] = field; });
          if (body.cut && Array.isArray(body.clear)) {
            const written = new Set(writes.map(([key]) => key));
            body.clear.forEach((key) => {
              const addrKey = String(key || "").toUpperCase();
              if (parseAddr(addrKey) && !written.has(addrKey)) delete sheet.cells[addrKey];
            });
          }
          touch(book);
          return { status: 200 };
        }
        if (action === "filter") {
          const column = String(body.column || "A").replace(/[^A-Za-z]/g, "").toUpperCase();
          sheet.filters = sheet.filters || {};
          if (body.clear) delete sheet.filters[column];
          else {
            sheet.filters[column] = {
              include: Array.isArray(body.include) ? body.include.map(String) : null,
              condition: String(body.condition || ""),
              value: String(body.conditionValue ?? body.value ?? ""),
            };
          }
          touch(book);
          return { status: 200 };
        }
        if (action === "pivot-apply" || (action === "refresh-pivot" && sheet.pivot)) {
          if (!sheet.pivot) return { status: 400, error: "Not a pivot worksheet" };
          const trial = { ...sheet.pivot };
          if (action === "pivot-apply") {
            trial.rows = String(body.rows || "");
            trial.columns = String(body.columns || "");
            trial.values = String(body.values || "");
            trial.summarize = String(body.summarize || "SUM");
          }
          const built = buildPivot(book, { ...sheet, pivot: trial });
          if (built.error) return { status: 400, error: built.error };
          snapshot(book);
          sheet.pivot = trial;
          sheet.cells = built.cells;
          touch(book);
          return { status: 200 };
        }
        if (action === "sort") {
          const header = body.header === true;
          const column = String(body.column || "A").toUpperCase();
          const descending = body.order === "Descending";
          const compareValues = (left, right) => {
            const a = String(left ?? "");
            const b = String(right ?? "");
            const an = Number(a);
            const bn = Number(b);
            if (a !== "" && b !== "" && !Number.isNaN(an) && !Number.isNaN(bn)) return an - bn;
            const ad = Date.parse(a);
            const bd = Date.parse(b);
            if (a !== "" && b !== "" && Number.isFinite(ad) && Number.isFinite(bd) && /[-/]/.test(a) && /[-/]/.test(b)) return ad - bd;
            return a.localeCompare(b);
          };
          const anchor = parseAddr(body.anchor);
          const focus = parseAddr(body.focus);
          const ranged = anchor && focus && (anchor.col !== focus.col || anchor.row !== focus.row);
          if (ranged) {
            const c1 = Math.min(anchor.col, focus.col);
            const c2 = Math.max(anchor.col, focus.col);
            const r1 = Math.min(anchor.row, focus.row);
            const r2 = Math.max(anchor.row, focus.row);
            const start = header ? r1 + 1 : r1;
            if (start > r2) return { status: 200 };
            const records = [];
            for (let row = start; row <= r2; row += 1) {
              const values = {};
              for (let col = 0; col < COLS; col += 1) values[colName(col)] = cellRaw(sheet, addr(col, row));
              records.push(values);
            }
            snapshot(book);
            records.sort((left, right) => {
              const cmp = compareValues(left[column], right[column]);
              return descending ? -cmp : cmp;
            });
            records.forEach((record, index) => {
              const row = start + index;
              for (let col = 0; col < COLS; col += 1) {
                const key = addr(col, row);
                const value = record[colName(col)] || "";
                if (value) sheet.cells[key] = value;
                else delete sheet.cells[key];
              }
            });
            touch(book);
            return { status: 200 };
          }
          const records = [];
          for (let row = header ? 2 : 1; row <= ROWS; row += 1) {
            const values = {};
            for (let col = 0; col < COLS; col += 1) values[colName(col)] = cellRaw(sheet, addr(col, row));
            if (Object.values(values).some((item) => item !== "")) records.push(values);
          }
          snapshot(book);
          records.sort((left, right) => {
            const cmp = compareValues(left[column], right[column]);
            return descending ? -cmp : cmp;
          });
          for (let row = header ? 2 : 1; row <= ROWS; row += 1) {
            const record = records[row - (header ? 2 : 1)];
            for (let col = 0; col < COLS; col += 1) {
              const key = addr(col, row);
              const value = record ? record[colName(col)] : "";
              if (value) sheet.cells[key] = value;
              else delete sheet.cells[key];
            }
          }
          touch(book);
          return { status: 200 };
        }
        if (action === "undo" || action === "redo") {
          const from = action === "undo" ? book.undo : book.redo;
          const to = action === "undo" ? book.redo : book.undo;
          const saved = from.pop();
          if (!saved) return { status: 400, error: "Nothing to undo" };
          to.push(JSON.stringify({ sheets: book.sheets, active: book.active, name: book.name }));
          const restored = JSON.parse(saved);
          book.sheets = restored.sheets;
          book.active = restored.active;
          book.name = restored.name;
          return { status: 200 };
        }
        if (action === "import") {
          const rows = parseCsv(String(body.csv || ""));
          if (!rows) return { status: 400, error: "Invalid CSV file format. Import failed." };
          const imported = blankSheet("Sheet1");
          rows.forEach((fields, rowIndex) => {
            fields.forEach((field, colIndex) => {
              if (field !== "") imported.cells[addr(colIndex, rowIndex + 1)] = field;
            });
          });
          const newId = randomUUID().slice(0, 8);
          draft.workbooks.push({
            id: newId,
            name: String(body.name || "Imported workbook"),
            updated: "just now",
            active: "Sheet1",
            undo: [],
            redo: [],
            sheets: [imported],
          });
          return { status: 200, id: newId };
        }
        if (action === "refresh-pivot") {
          if (!sheet.pivot) return { status: 200 };
          const built = buildPivot(book, sheet);
          if (built.error) return { status: 400, error: built.error };
          snapshot(book);
          sheet.cells = built.cells;
          touch(book);
          return { status: 200 };
        }
        if (action === "validation") {
          snapshot(book);
          const start = String(body.start || sheet.selection || "A1").toUpperCase();
          sheet.validation = {
            type: String(body.type || "Number range"),
            minimum: String(body.minimum ?? "0"),
            maximum: String(body.maximum ?? "100"),
            values: String(body.values || ""),
            cell: start,
            start,
            end: String(body.end || start).toUpperCase(),
          };
          touch(book);
          return { status: 200 };
        }
        if (action === "delete-rule") {
          snapshot(book);
          delete sheet.validation;
          touch(book);
          return { status: 200 };
        }
        return { status: 404, error: "Not found" };
      });
      sendJson(response, updated.status, updated.status === 200 ? { ok: true, ...updated } : { error: updated.error });
      return true;
    }
  }
  if (parts[0] === "api") {
    sendJson(response, 404, { error: "Not found" });
    return true;
  }
  return false;
}

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url || "/", "http://localhost");
    if (await handleApi(request, response, url)) return;
    const requested = url.pathname === "/" ? "index.html" : url.pathname.replace(/^\/+/, "");
    const candidate = path.resolve(publicDir, requested);
    const safePath = candidate.startsWith(publicDir + path.sep) ? candidate : path.join(publicDir, "index.html");
    let filePath = safePath;
    let body;
    try { body = await readFile(filePath); }
    catch { filePath = path.join(publicDir, "index.html"); body = await readFile(filePath); }
    response.writeHead(200, { "content-type": types[path.extname(filePath)] || "application/octet-stream" });
    response.end(body);
  } catch (error) {
    if (!response.headersSent) sendJson(response, error.status || 500, { error: String(error.message || error) });
  }
});

await mkdir(path.dirname(dataPath), { recursive: true });
try {
  const existing = JSON.parse(await readFile(dataPath, "utf8"));
  if (!existing.workbooks) await saveState(seedState());
} catch (error) {
  if (!error || error.code !== "ENOENT") throw error;
  await saveState(seedState());
}
server.listen(port, host);
