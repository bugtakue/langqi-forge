const app = document.querySelector("#app");

const COLUMN_COUNT = 20;
const ROW_COUNT = 30;
let workbook = null;
let saveQueue = Promise.resolve();
let editing = null;
let pointerStart = null;
let pointerLast = null;
let suppressClick = false;
let internalClipboard = null;
let pendingPaste = null;
let pasteQueue = Promise.resolve();
let undoStack = [];
let redoStack = [];

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "content-type": "application/json", ...(options.headers || {}) },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return response.json();
}

function updatedText(value) {
  return `Last updated: ${new Date(value).toLocaleString()}`;
}

function columnLetters(index) {
  let letters = "";
  let remaining = index;
  do {
    letters = String.fromCharCode(65 + (remaining % 26)) + letters;
    remaining = Math.floor(remaining / 26) - 1;
  } while (remaining >= 0);
  return letters;
}

function columnIndex(letters) {
  return letters
    .toUpperCase()
    .split("")
    .reduce((value, letter) => value * 26 + letter.charCodeAt(0) - 64, 0) - 1;
}

function parseCoordinate(coordinate) {
  const match = /^([A-Z]+)(\d+)$/i.exec(coordinate);
  if (!match || Number(match[2]) < 1) throw new Error("#REF!");
  return { column: columnIndex(match[1]), row: Number(match[2]) - 1 };
}

function coordinateAt(column, row) {
  if (column < 0 || row < 0) return null;
  return `${columnLetters(column)}${row + 1}`;
}

function activeSheet() {
  return workbook?.sheets.find((sheet) => sheet.id === workbook.activeSheetId) || workbook?.sheets[0];
}

function historySnapshot() {
  return structuredClone({
    name: workbook.name,
    sheets: workbook.sheets,
    activeSheetId: workbook.activeSheetId,
  });
}

function recordHistory() {
  undoStack.push(historySnapshot());
  if (undoStack.length > 50) undoStack.shift();
  redoStack = [];
}

async function restoreHistory(source, destination) {
  if (!source.length) return;
  destination.push(historySnapshot());
  const snapshot = source.pop();
  workbook.name = snapshot.name;
  workbook.sheets = snapshot.sheets;
  workbook.activeSheetId = snapshot.activeSheetId;
  await queueSave();
  renderEditor();
}

function rawCell(sheet, coordinate) {
  return Object.hasOwn(sheet.cells || {}, coordinate) ? String(sheet.cells[coordinate]) : "";
}

function validationError(sheet, coordinate, value) {
  const rule = sheet.validations?.[coordinate];
  if (!rule || value === "") return "";
  if (rule.type === "number") {
    const number = Number(value);
    if (!Number.isFinite(number) || number < Number(rule.minimum) || number > Number(rule.maximum)) {
      return `Enter a number from ${rule.minimum} to ${rule.maximum}`;
    }
  }
  if (rule.type === "dropdown" && !rule.values.includes(String(value))) {
    return `Choose one of: ${rule.values.join(", ")}`;
  }
  return "";
}

function numeric(value) {
  if (value === "" || typeof value === "boolean") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function formulaError(code) {
  const error = new Error(code);
  error.formulaCode = code;
  return error;
}

function rangeValues(sheet, start, end, stack) {
  let first;
  let last;
  try {
    first = parseCoordinate(start.replaceAll("$", ""));
    last = parseCoordinate(end.replaceAll("$", ""));
  } catch {
    throw formulaError("#REF!");
  }
  const values = [];
  for (let row = Math.min(first.row, last.row); row <= Math.max(first.row, last.row); row += 1) {
    for (
      let column = Math.min(first.column, last.column);
      column <= Math.max(first.column, last.column);
      column += 1
    ) {
      const value = evaluateCell(sheet, coordinateAt(column, row), stack);
      if (String(value).startsWith("#")) throw formulaError(String(value));
      const number = numeric(value);
      if (number !== null) values.push(number);
    }
  }
  return values;
}

function evaluateFormula(sheet, coordinate, formula, stack) {
  let expression = formula.slice(1).trim();
  if (!expression) throw formulaError("#ERROR!");
  if (expression.includes("#REF!")) throw formulaError("#REF!");

  const knownFunctions = new Set(["SUM", "AVERAGE", "COUNT", "MIN", "MAX"]);
  const functionNames = [...expression.matchAll(/([A-Z_][A-Z0-9_]*)\s*\(/gi)].map((match) => match[1]);
  if (functionNames.some((name) => !knownFunctions.has(name.toUpperCase()))) {
    throw formulaError("#NAME?");
  }

  let previous;
  do {
    previous = expression;
    expression = expression.replace(
      /\b(SUM|AVERAGE|COUNT|MIN|MAX)\s*\(\s*(\$?[A-Z]+\$?\d+)\s*:\s*(\$?[A-Z]+\$?\d+)\s*\)/gi,
      (_match, functionName, start, end) => {
        const values = rangeValues(sheet, start, end, stack);
        switch (functionName.toUpperCase()) {
          case "SUM":
            return String(values.reduce((sum, value) => sum + value, 0));
          case "AVERAGE":
            if (!values.length) throw formulaError("#DIV/0!");
            return String(values.reduce((sum, value) => sum + value, 0) / values.length);
          case "COUNT":
            return String(values.length);
          case "MIN":
            return values.length ? String(Math.min(...values)) : "0";
          case "MAX":
            return values.length ? String(Math.max(...values)) : "0";
          default:
            throw formulaError("#NAME?");
        }
      },
    );
  } while (expression !== previous);

  if (/\b(?:SUM|AVERAGE|COUNT|MIN|MAX)\s*\(/i.test(expression)) {
    throw formulaError("#ERROR!");
  }

  expression = expression.replace(/\$?[A-Z]+\$?\d+/gi, (reference) => {
    const normalized = reference.replaceAll("$", "").toUpperCase();
    try {
      parseCoordinate(normalized);
    } catch {
      throw formulaError("#REF!");
    }
    const value = evaluateCell(sheet, normalized, stack);
    if (String(value).startsWith("#")) throw formulaError(String(value));
    if (value === "") return "0";
    const number = numeric(value);
    if (number === null) throw formulaError("#ERROR!");
    return String(number);
  });

  if (/[A-Z_]/i.test(expression)) throw formulaError("#NAME?");
  if (!/^[\d.eE+\-*/()\s]+$/.test(expression)) throw formulaError("#ERROR!");

  let result;
  try {
    result = Function(`"use strict"; return (${expression});`)();
  } catch {
    throw formulaError("#ERROR!");
  }
  if (typeof result !== "number" || Number.isNaN(result)) throw formulaError("#ERROR!");
  if (!Number.isFinite(result)) throw formulaError("#DIV/0!");
  const rounded = Number(result.toPrecision(12));
  return Object.is(rounded, -0) ? "0" : String(rounded);
}

function evaluateCell(sheet, coordinate, stack = new Set()) {
  const raw = rawCell(sheet, coordinate);
  if (raw.startsWith("'")) return raw.slice(1);
  if (!raw.startsWith("=")) return raw;
  if (stack.has(coordinate)) return "#REF!";
  const nextStack = new Set(stack);
  nextStack.add(coordinate);
  try {
    return evaluateFormula(sheet, coordinate, raw, nextStack);
  } catch (error) {
    return error.formulaCode || "#ERROR!";
  }
}

function rangeCoordinates(start, end) {
  const first = parseCoordinate(start);
  const last = parseCoordinate(end);
  const coordinates = [];
  for (let row = Math.min(first.row, last.row); row <= Math.max(first.row, last.row); row += 1) {
    for (
      let column = Math.min(first.column, last.column);
      column <= Math.max(first.column, last.column);
      column += 1
    ) {
      coordinates.push(coordinateAt(column, row));
    }
  }
  return coordinates;
}

function applySelectionToDom(sheet) {
  const selected = new Set(sheet.selection || [sheet.selected || "A1"]);
  for (const cell of document.querySelectorAll('[role="gridcell"][data-coordinate]')) {
    cell.setAttribute("aria-selected", selected.has(cell.dataset.coordinate) ? "true" : "false");
  }
  const formula = document.querySelector("#formula-bar");
  if (formula) formula.value = rawCell(sheet, sheet.selected || "A1");
}

function queueSave() {
  if (!workbook) return Promise.resolve();
  const id = workbook.id;
  const snapshot = structuredClone(workbook);
  saveQueue = saveQueue.then(async () => {
    const saved = await request(`/api/workbooks/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify(snapshot),
    });
    if (workbook?.id === id) workbook.updatedAt = saved.updatedAt;
    return saved;
  });
  return saveQueue;
}

function setSingleSelection(coordinate, { persist = true } = {}) {
  const sheet = activeSheet();
  sheet.selected = coordinate;
  sheet.selection = [coordinate];
  applySelectionToDom(sheet);
  if (persist) void queueSave();
}

function setRangeSelection(start, end, { persist = true } = {}) {
  const sheet = activeSheet();
  sheet.selected = start;
  sheet.selection = rangeCoordinates(start, end);
  applySelectionToDom(sheet);
  if (persist) void queueSave();
}

function suppressImmediateDragClick() {
  suppressClick = true;
  setTimeout(() => {
    suppressClick = false;
  }, 0);
}

function showMessage(message) {
  document.querySelector(".toast")?.remove();
  const node = document.createElement("div");
  node.className = "toast error";
  node.setAttribute("role", "alert");
  node.textContent = message;
  document.body.append(node);
}

function closeOverlays() {
  document.querySelectorAll(".menu, .backdrop").forEach((node) => node.remove());
}

function showDialog(title, content) {
  closeOverlays();
  const backdrop = document.createElement("div");
  backdrop.className = "backdrop";
  backdrop.innerHTML = `
    <section class="dialog" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}">
      <h2>${escapeHtml(title)}</h2>
      ${content}
    </section>`;
  document.body.append(backdrop);
  return backdrop.querySelector('[role="dialog"]');
}

function choiceMarkup(id, label, options, selected = "") {
  const selectedOption = options.find((option) => option.value === selected) || options[0];
  return `<label for="${id}">${escapeHtml(label)}
    <button id="${id}" class="secondary" type="button" aria-label="${escapeHtml(label)}" aria-haspopup="listbox" data-value="${escapeHtml(selectedOption?.value || "")}">${escapeHtml(selectedOption?.label || "")}</button>
  </label>
  <div id="${id}-options" class="option-list" role="listbox" hidden>
    ${options.map((option) => `<button type="button" role="option" data-choice="${id}" data-value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</button>`).join("")}
  </div>`;
}

function wireChoice(scope, id, onChange = () => {}) {
  const control = scope.querySelector(`#${id}`);
  const list = scope.querySelector(`#${id}-options`);
  control.addEventListener("click", () => {
    list.hidden = false;
  });
  for (const option of list.querySelectorAll(`[data-choice="${id}"]`)) {
    option.addEventListener("click", () => {
      control.dataset.value = option.dataset.value;
      control.textContent = option.textContent;
      list.hidden = true;
      onChange(option.dataset.value);
    });
  }
  return control;
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  let closedQuote = false;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quoted) {
      if (character === '"') {
        if (text[index + 1] === '"') {
          field += '"';
          index += 1;
        } else {
          quoted = false;
          closedQuote = true;
        }
      } else {
        field += character;
      }
      continue;
    }
    if (character === '"') {
      if (field || closedQuote) throw new Error("invalid CSV");
      quoted = true;
      continue;
    }
    if (closedQuote && character !== "," && character !== "\r" && character !== "\n") {
      throw new Error("invalid CSV");
    }
    if (character === ",") {
      row.push(field);
      field = "";
      closedQuote = false;
    } else if (character === "\n" || character === "\r") {
      if (character === "\r" && text[index + 1] === "\n") index += 1;
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
      closedQuote = false;
    } else {
      field += character;
    }
  }
  if (quoted) throw new Error("invalid CSV");
  if (field || row.length || !rows.length) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

function rowsToCells(rows) {
  const cells = {};
  rows.forEach((row, rowIndex) => {
    row.forEach((value, column) => {
      cells[coordinateAt(column, rowIndex)] = value.startsWith("=") ? `'${value}` : value;
    });
  });
  return cells;
}

function csvEscape(value) {
  const text = String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function sheetCsv(sheet) {
  const coordinates = Object.keys(sheet.cells || {});
  if (!coordinates.length) return "";
  let maxColumn = 0;
  let maxRow = 0;
  for (const coordinate of coordinates) {
    const parsed = parseCoordinate(coordinate);
    maxColumn = Math.max(maxColumn, parsed.column);
    maxRow = Math.max(maxRow, parsed.row);
  }
  const rows = [];
  for (let row = 0; row <= maxRow; row += 1) {
    const values = [];
    for (let column = 0; column <= maxColumn; column += 1) {
      values.push(csvEscape(evaluateCell(sheet, coordinateAt(column, row))));
    }
    rows.push(values.join(","));
  }
  return rows.join("\n");
}

function rowPassesFilter(sheet, row) {
  const filter = sheet.filter;
  if (!filter || row === filter.minRow || row < filter.minRow || row > filter.maxRow) return true;
  for (const [columnText, rule] of Object.entries(filter.conditions || {})) {
    const value = evaluateCell(sheet, coordinateAt(Number(columnText), row));
    if (rule.selectedValues && !rule.selectedValues.includes(String(value))) return false;
    const target = String(rule.value || "");
    switch (rule.condition) {
      case "contains":
        if (!String(value).toLowerCase().includes(target.toLowerCase())) return false;
        break;
      case "greater_than":
        if (numeric(value) === null || numeric(value) <= Number(target)) return false;
        break;
      case "date_before":
        if (!value || String(value) >= target) return false;
        break;
      case "is_empty":
        if (String(value) !== "") return false;
        break;
      case "is_not_empty":
        if (String(value) === "") return false;
        break;
      default:
        break;
    }
  }
  return true;
}

function pivotSource(sheet) {
  if (!sheet.pivot) return null;
  return workbook.sheets.find((candidate) => candidate.id === sheet.pivot.sourceSheetId) || null;
}

function pivotHeaders(sheet) {
  const source = pivotSource(sheet);
  if (!source) return [];
  const headers = [];
  for (let column = sheet.pivot.range.minColumn; column <= sheet.pivot.range.maxColumn; column += 1) {
    headers.push({
      label: String(evaluateCell(source, coordinateAt(column, sheet.pivot.range.minRow))),
      column,
    });
  }
  return headers.filter((header) => header.label);
}

function aggregateValues(values, summary) {
  if (summary === "COUNT") return String(values.filter((value) => String(value) !== "").length);
  const numbers = values.map(numeric).filter((value) => value !== null);
  if (!numbers.length) return "";
  const sum = numbers.reduce((total, value) => total + value, 0);
  return summary === "AVERAGE" ? String(Number((sum / numbers.length).toPrecision(12))) : String(sum);
}

function buildPivotCells(sheet, candidate) {
  const source = pivotSource(sheet);
  if (!source) return { error: "Pivot source worksheet is unavailable" };
  const headers = pivotHeaders(sheet);
  const rowHeader = headers.find((header) => header.label === candidate.rowField);
  const valueHeader = headers.find((header) => header.label === candidate.valueField);
  const columnHeader = candidate.columnField
    ? headers.find((header) => header.label === candidate.columnField)
    : null;
  if (!rowHeader || !valueHeader || (candidate.columnField && !columnHeader)) {
    return { error: "Pivot field is no longer available. Select a new field." };
  }

  const records = [];
  for (let row = sheet.pivot.range.minRow + 1; row <= sheet.pivot.range.maxRow; row += 1) {
    records.push({
      row: evaluateCell(source, coordinateAt(rowHeader.column, row)),
      column: columnHeader ? evaluateCell(source, coordinateAt(columnHeader.column, row)) : "",
      value: evaluateCell(source, coordinateAt(valueHeader.column, row)),
    });
  }
  if (["SUM", "AVERAGE"].includes(candidate.summary) && !records.some((record) => numeric(record.value) !== null)) {
    return { error: "Value field requires numeric values" };
  }

  const rowGroups = [...new Set(records.map((record) => String(record.row)))];
  const columnGroups = columnHeader ? [...new Set(records.map((record) => String(record.column)))] : [];
  const cells = {};
  cells.A1 = candidate.rowField;
  if (!columnHeader) {
    cells.B1 = `${candidate.summary} of ${candidate.valueField}`;
    rowGroups.forEach((group, index) => {
      cells[`A${index + 2}`] = group;
      cells[`B${index + 2}`] = aggregateValues(
        records.filter((record) => String(record.row) === group).map((record) => record.value),
        candidate.summary,
      );
    });
    const totalRow = rowGroups.length + 2;
    cells[`A${totalRow}`] = "Grand Total";
    cells[`B${totalRow}`] = aggregateValues(records.map((record) => record.value), candidate.summary);
  } else {
    columnGroups.forEach((group, index) => {
      cells[`${columnLetters(index + 1)}1`] = group;
    });
    const totalColumn = columnGroups.length + 1;
    cells[`${columnLetters(totalColumn)}1`] = "Grand Total";
    rowGroups.forEach((rowGroup, rowIndex) => {
      const targetRow = rowIndex + 2;
      cells[`A${targetRow}`] = rowGroup;
      columnGroups.forEach((columnGroup, columnIndexValue) => {
        cells[`${columnLetters(columnIndexValue + 1)}${targetRow}`] = aggregateValues(
          records
            .filter(
              (record) => String(record.row) === rowGroup && String(record.column) === columnGroup,
            )
            .map((record) => record.value),
          candidate.summary,
        );
      });
      cells[`${columnLetters(totalColumn)}${targetRow}`] = aggregateValues(
        records.filter((record) => String(record.row) === rowGroup).map((record) => record.value),
        candidate.summary,
      );
    });
    const totalRow = rowGroups.length + 2;
    cells[`A${totalRow}`] = "Grand Total";
    columnGroups.forEach((columnGroup, columnIndexValue) => {
      cells[`${columnLetters(columnIndexValue + 1)}${totalRow}`] = aggregateValues(
        records.filter((record) => String(record.column) === columnGroup).map((record) => record.value),
        candidate.summary,
      );
    });
    cells[`${columnLetters(totalColumn)}${totalRow}`] = aggregateValues(
      records.map((record) => record.value),
      candidate.summary,
    );
  }
  return { cells };
}

async function renderHome() {
  workbook = null;
  const workbooks = await request("/api/workbooks");
  app.innerHTML = `
    <header class="topbar"><h1>Sheet Workspace</h1></header>
    <main class="home">
      <h2>Your workbooks</h2>
      <div class="home-actions">
        <button class="primary" type="button" id="new-workbook">New blank workbook</button>
        <button class="secondary" type="button" id="import-csv">Import CSV</button>
      </div>
      <ul class="workbook-list" aria-label="Saved workbooks">
        ${workbooks
          .map(
            (item) => `<li><a href="/workbooks/${encodeURIComponent(item.id)}" aria-label="${escapeHtml(item.name)}">
              <span>${escapeHtml(item.name)}</span>
              <span aria-hidden="true">${escapeHtml(updatedText(item.updatedAt))}</span>
            </a></li>`,
          )
          .join("")}
      </ul>
    </main>`;

  document.querySelector("#new-workbook").addEventListener("click", () => {
    const dialog = showDialog(
      "New blank workbook",
      `<p>Create a workbook with one empty worksheet.</p>
       <div class="dialog-actions">
         <button class="secondary" type="button" data-close>Cancel</button>
         <button class="primary" type="button" id="confirm-create">Create</button>
       </div>`,
    );
    dialog.querySelector("[data-close]").addEventListener("click", closeOverlays);
    dialog.querySelector("#confirm-create").addEventListener("click", async () => {
      const created = await request("/api/workbooks", {
        method: "POST",
        body: JSON.stringify({ name: "Untitled workbook" }),
      });
      window.location.assign(`/workbooks/${encodeURIComponent(created.id)}`);
    });
  });

  document.querySelector("#import-csv").addEventListener("click", () => {
    const dialog = showDialog(
      "Import CSV",
      `<label for="csv-file">CSV file<input id="csv-file" type="file" accept=".csv,text/csv" /></label>
       <p class="error" role="alert" id="csv-error"></p>
       <div class="dialog-actions">
         <button class="secondary" type="button" data-close>Cancel</button>
         <button class="primary" type="button" id="confirm-import">Confirm import</button>
       </div>`,
    );
    dialog.querySelector("[data-close]").addEventListener("click", closeOverlays);
    dialog.querySelector("#confirm-import").addEventListener("click", async () => {
      const input = dialog.querySelector("#csv-file");
      const errorNode = dialog.querySelector("#csv-error");
      if (!input.files?.length) {
        errorNode.textContent = "Choose a CSV file.";
        return;
      }
      try {
        const file = input.files[0];
        const cells = rowsToCells(parseCsv(await file.text()));
        const name = file.name.replace(/\.csv$/i, "") || "Imported workbook";
        const created = await request("/api/workbooks", {
          method: "POST",
          body: JSON.stringify({ name, cells }),
        });
        window.location.assign(`/workbooks/${encodeURIComponent(created.id)}`);
      } catch {
        errorNode.textContent = "Invalid CSV file format. Import failed.";
      }
    });
  });
}

function gridMarkup(sheet) {
  const headers = Array.from({ length: COLUMN_COUNT }, (_, column) => {
    const name = columnLetters(column);
    return `<th role="columnheader" aria-label="${name}" data-column="${column}">${name}</th>`;
  }).join("");
  const rows = Array.from({ length: ROW_COUNT }, (_, row) => {
    const cells = Array.from({ length: COLUMN_COUNT }, (_unused, column) => {
      const coordinate = coordinateAt(column, row);
      const selected = (sheet.selection || [sheet.selected || "A1"]).includes(coordinate);
      const rule = sheet.validations?.[coordinate];
      const dropdown = rule?.type === "dropdown"
        ? `<button class="validation-trigger" type="button" aria-label="Open dropdown for ${coordinate}" data-validation-dropdown="${coordinate}"></button>`
        : "";
      const filterButton = sheet.filter
        && row === sheet.filter.minRow
        && column >= sheet.filter.minColumn
        && column <= sheet.filter.maxColumn
        ? `<button class="filter-trigger" type="button" aria-label="Filter ${escapeHtml(evaluateCell(sheet, coordinate) || columnLetters(column))}" data-filter-column="${column}"></button>`
        : "";
      return `<td role="gridcell" aria-label="${coordinate}" aria-selected="${selected}" tabindex="-1" draggable="true" data-coordinate="${coordinate}"><span>${escapeHtml(evaluateCell(sheet, coordinate))}</span>${dropdown}${filterButton}</td>`;
    }).join("");
    return `<tr role="row" class="${rowPassesFilter(sheet, row) ? "" : "filtered-out"}"><th role="rowheader" aria-label="${row + 1}" data-row="${row}">${row + 1}</th>${cells}</tr>`;
  }).join("");
  return `<table class="sheet-grid" role="grid" aria-label="Worksheet grid" aria-multiselectable="true"><thead><tr><th></th>${headers}</tr></thead><tbody>${rows}</tbody></table>`;
}

function pivotEditorMarkup(sheet) {
  if (!sheet.pivot) return "";
  const fields = pivotHeaders(sheet).map((header) => ({ value: header.label, label: header.label }));
  const optionalFields = [{ value: "", label: "None" }, ...fields];
  return `<section class="pivot-editor" role="region" aria-label="Pivot table editor">
    <h2>Pivot table editor</h2>
    ${choiceMarkup("pivot-rows", "Rows", fields, sheet.pivot.rowField || fields[0]?.value)}
    ${choiceMarkup("pivot-columns", "Columns", optionalFields, sheet.pivot.columnField || "")}
    ${choiceMarkup("pivot-values", "Values", fields, sheet.pivot.valueField || fields[0]?.value)}
    ${choiceMarkup("pivot-summary", "Summarize by", [
      { value: "SUM", label: "SUM" },
      { value: "COUNT", label: "COUNT" },
      { value: "AVERAGE", label: "AVERAGE" },
    ], sheet.pivot.summary || "SUM")}
    <div class="dialog-actions">
      <button class="secondary" type="button" id="refresh-pivot">Refresh pivot table</button>
      <button class="primary" type="button" id="apply-pivot">Apply</button>
    </div>
  </section>`;
}

function renderEditor() {
  const sheet = activeSheet();
  const selected = sheet.selected || "A1";
  app.innerHTML = `
    <header class="topbar">
      <a href="/" class="secondary">Workbooks</a>
      <h1>${escapeHtml(workbook.name)}</h1>
      <span class="status">${escapeHtml(updatedText(workbook.updatedAt))}</span>
      <span class="spacer"></span>
      <button class="secondary" type="button" id="rename-workbook">Rename workbook</button>
      <button class="secondary" type="button" id="export-csv">Export CSV</button>
    </header>
    <div class="toolbar">
      <button class="secondary" type="button" id="data-menu">Data</button>
      <button class="secondary" type="button" id="undo" ${undoStack.length ? "" : "disabled"}>Undo</button>
      <button class="secondary" type="button" id="redo" ${redoStack.length ? "" : "disabled"}>Redo</button>
    </div>
    <div class="formula-row">
      <label for="formula-bar">Formula bar</label>
      <input id="formula-bar" aria-label="Formula bar" value="${escapeHtml(rawCell(sheet, selected))}" autocomplete="off" />
    </div>
    ${pivotEditorMarkup(sheet)}
    <div class="grid-wrap">${gridMarkup(sheet)}</div>
    <div class="tabs" role="tablist" aria-label="Worksheets">
      <button class="primary" type="button" id="add-sheet">Add sheet</button>
      ${workbook.sheets
        .map(
          (item) => `<span class="tab-wrap">
            <button type="button" role="tab" aria-selected="${item.id === workbook.activeSheetId}" data-sheet-id="${escapeHtml(item.id)}">${escapeHtml(item.name)}</button>
            <button type="button" class="icon-button" aria-label="Worksheet options for ${escapeHtml(item.name)}" data-sheet-options="${escapeHtml(item.id)}">⋮</button>
          </span>`,
        )
        .join("")}
    </div>`;
  wireEditor();
}

async function commitCell(coordinate, value, { resetSelection = false, record = true } = {}) {
  const sheet = activeSheet();
  const message = validationError(sheet, coordinate, String(value));
  if (message) {
    renderEditor();
    showMessage(message);
    return false;
  }
  if (record && rawCell(sheet, coordinate) !== String(value)) recordHistory();
  sheet.cells ||= {};
  sheet.cells[coordinate] = String(value);
  if (resetSelection) {
    sheet.selected = "A1";
    sheet.selection = ["A1"];
  }
  await queueSave();
  renderEditor();
  return true;
}

function startInlineEdit(cell) {
  if (editing) return;
  const coordinate = cell.dataset.coordinate;
  const original = rawCell(activeSheet(), coordinate);
  cell.textContent = "";
  const input = document.createElement("input");
  input.type = "text";
  input.setAttribute("aria-label", `Edit ${coordinate}`);
  input.value = original;
  cell.append(input);
  editing = { coordinate, input, original, done: false };
  input.focus();
  input.select();

  const finish = async (commit) => {
    if (!editing || editing.input !== input || editing.done) return;
    editing.done = true;
    const value = input.value;
    editing = null;
    if (commit) await commitCell(coordinate, value);
    else renderEditor();
  };
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void finish(true);
    } else if (event.key === "Escape") {
      event.preventDefault();
      void finish(false);
    }
  });
  input.addEventListener("blur", () => setTimeout(() => void finish(true), 0));
}

function selectedBounds(sheet) {
  const coordinates = sheet.selection?.length ? sheet.selection : [sheet.selected || "A1"];
  const parsed = coordinates.map(parseCoordinate);
  return {
    minColumn: Math.min(...parsed.map((item) => item.column)),
    maxColumn: Math.max(...parsed.map((item) => item.column)),
    minRow: Math.min(...parsed.map((item) => item.row)),
    maxRow: Math.max(...parsed.map((item) => item.row)),
  };
}

function adjustFormula(raw, columnDelta, rowDelta) {
  if (!raw.startsWith("=")) return raw;
  let invalid = false;
  const adjusted = raw.replace(/(\$?)([A-Z]+)(\$?)(\d+)/gi, (_match, absoluteColumn, letters, absoluteRow, rowText) => {
    let column = columnIndex(letters);
    let row = Number(rowText) - 1;
    if (!absoluteColumn) column += columnDelta;
    if (!absoluteRow) row += rowDelta;
    const coordinate = coordinateAt(column, row);
    if (!coordinate) {
      invalid = true;
      return "#REF!";
    }
    const parsed = parseCoordinate(coordinate);
    return `${absoluteColumn ? "$" : ""}${columnLetters(parsed.column)}${absoluteRow ? "$" : ""}${parsed.row + 1}`;
  });
  return invalid ? adjusted : adjusted;
}

async function copySelection(cut) {
  const sheet = activeSheet();
  const bounds = selectedBounds(sheet);
  const matrix = [];
  const sourceCoordinates = [];
  for (let row = bounds.minRow; row <= bounds.maxRow; row += 1) {
    const values = [];
    for (let column = bounds.minColumn; column <= bounds.maxColumn; column += 1) {
      const coordinate = coordinateAt(column, row);
      sourceCoordinates.push(coordinate);
      values.push({ raw: rawCell(sheet, coordinate), coordinate });
    }
    matrix.push(values);
  }
  const text = matrix.map((row) => row.map((cell) => cell.raw).join("\t")).join("\n");
  internalClipboard = { matrix, text, cut, sourceCoordinates, sourceSheetId: sheet.id };
  await navigator.clipboard.writeText(text).catch(() => {});
}

function parseTabular(text) {
  return text.replaceAll("\r\n", "\n").replaceAll("\r", "\n").split("\n").map((row) => row.split("\t"));
}

async function pasteAt(start, text) {
  const sheet = activeSheet();
  const destination = parseCoordinate(start);
  const useInternal = internalClipboard && internalClipboard.text === text;
  const matrix = useInternal ? internalClipboard.matrix : parseTabular(text).map((row) => row.map((raw) => ({ raw })));
  const nextCells = { ...(sheet.cells || {}) };
  const proposed = [];
  for (let row = 0; row < matrix.length; row += 1) {
    for (let column = 0; column < matrix[row].length; column += 1) {
      const target = coordinateAt(destination.column + column, destination.row + row);
      if (!target) continue;
      const source = matrix[row][column];
      let raw = source.raw;
      if (useInternal && !internalClipboard.cut && source.coordinate) {
        const from = parseCoordinate(source.coordinate);
        const to = parseCoordinate(target);
        raw = adjustFormula(raw, to.column - from.column, to.row - from.row);
      }
      proposed.push({ coordinate: target, raw });
      const message = validationError(sheet, target, raw);
      if (message) {
        renderEditor();
        showMessage(message);
        return;
      }
      nextCells[target] = raw;
    }
  }
  if (useInternal && internalClipboard.cut && internalClipboard.sourceSheetId === sheet.id) {
    const targets = new Set();
    for (let row = 0; row < matrix.length; row += 1) {
      for (let column = 0; column < matrix[row].length; column += 1) {
        targets.add(coordinateAt(destination.column + column, destination.row + row));
      }
    }
    for (const coordinate of internalClipboard.sourceCoordinates) {
      if (!targets.has(coordinate)) nextCells[coordinate] = "";
    }
    internalClipboard = null;
  }
  if (proposed.some(({ coordinate, raw }) => rawCell(sheet, coordinate) !== raw)) recordHistory();
  sheet.cells = nextCells;
  await queueSave();
  renderEditor();
}

function enqueuePaste(start, textPromise) {
  pasteQueue = pasteQueue
    .catch(() => undefined)
    .then(async () => pasteAt(start, await textPromise));
  return pasteQueue;
}

async function clipboardText(event) {
  const eventText = event?.clipboardData?.getData("text/plain");
  if (eventText !== undefined && eventText !== "") return eventText;
  return navigator.clipboard.readText();
}

function showContextMenu(cell, x, y) {
  document.querySelector(".menu")?.remove();
  const menu = document.createElement("div");
  menu.className = "menu";
  menu.setAttribute("role", "menu");
  menu.style.left = `${x}px`;
  menu.style.top = `${y}px`;
  menu.innerHTML = `<button role="menuitem" type="button">Paste</button>`;
  menu.querySelector("button").addEventListener("click", async () => {
    const text = await clipboardText();
    menu.remove();
    await enqueuePaste(cell.dataset.coordinate, Promise.resolve(text));
  });
  document.body.append(menu);
}

function showDataValidation() {
  const sheet = activeSheet();
  const coordinates = sheet.selection?.length ? [...sheet.selection] : [sheet.selected || "A1"];
  const existing = sheet.validations?.[sheet.selected || coordinates[0]];
  const dialog = showDialog(
    "Data validation",
    `<label for="rule-type">Rule type
       <button id="rule-type" class="secondary" type="button" aria-label="Rule type" aria-haspopup="listbox"></button>
     </label>
     <div id="rule-type-options" class="option-list" role="listbox" hidden>
       <button type="button" role="option" data-rule-type="dropdown">Dropdown</button>
       <button type="button" role="option" data-rule-type="number">Number range</button>
     </div>
     <div id="rule-fields"></div>
     <p class="error" role="alert"></p>
     <div class="dialog-actions">
       <button class="secondary" type="button" data-delete-rule>Delete rule</button>
       <button class="secondary" type="button" data-close>Cancel</button>
       <button class="primary" type="button" data-save>Save</button>
     </div>`,
  );
  const typeInput = dialog.querySelector("#rule-type");
  typeInput.dataset.value = existing?.type || "dropdown";
  typeInput.textContent = typeInput.dataset.value === "number" ? "Number range" : "Dropdown";
  const selectedType = () => typeInput.dataset.value;
  const renderFields = () => {
    const fields = dialog.querySelector("#rule-fields");
    if (selectedType() === "number") {
      fields.innerHTML = `
        <label for="validation-minimum">Minimum<input id="validation-minimum" aria-label="Minimum" type="text" value="${escapeHtml(existing?.type === "number" ? existing.minimum : "")}" /></label>
        <label for="validation-maximum">Maximum<input id="validation-maximum" aria-label="Maximum" type="text" value="${escapeHtml(existing?.type === "number" ? existing.maximum : "")}" /></label>`;
    } else {
      fields.innerHTML = `<label for="validation-values">Allowed values<input id="validation-values" aria-label="Allowed values" type="text" value="${escapeHtml(existing?.type === "dropdown" ? existing.values.join(", ") : "")}" /></label>`;
    }
  };
  renderFields();
  typeInput.addEventListener("click", () => {
    dialog.querySelector("#rule-type-options").hidden = false;
  });
  for (const option of dialog.querySelectorAll("[data-rule-type]")) {
    option.addEventListener("click", () => {
      typeInput.dataset.value = option.dataset.ruleType;
      typeInput.textContent = option.textContent;
      dialog.querySelector("#rule-type-options").hidden = true;
      renderFields();
    });
  }
  dialog.querySelector("[data-close]").addEventListener("click", closeOverlays);
  dialog.querySelector("[data-delete-rule]").addEventListener("click", async () => {
    if (coordinates.some((coordinate) => sheet.validations?.[coordinate])) recordHistory();
    sheet.validations ||= {};
    for (const coordinate of coordinates) delete sheet.validations[coordinate];
    await queueSave();
    closeOverlays();
    renderEditor();
  });
  dialog.querySelector("[data-save]").addEventListener("click", async () => {
    let rule;
    if (selectedType() === "number") {
      const minimum = dialog.querySelector("#validation-minimum").value.trim();
      const maximum = dialog.querySelector("#validation-maximum").value.trim();
      if (!Number.isFinite(Number(minimum)) || !Number.isFinite(Number(maximum))) {
        dialog.querySelector(".error").textContent = "Minimum and maximum must be numbers";
        return;
      }
      rule = { type: "number", minimum, maximum };
    } else {
      const values = dialog
        .querySelector("#validation-values")
        .value.split(",")
        .map((value) => value.trim())
        .filter(Boolean);
      if (!values.length) {
        dialog.querySelector(".error").textContent = "Enter at least one allowed value";
        return;
      }
      rule = { type: "dropdown", values };
    }
    recordHistory();
    sheet.validations ||= {};
    for (const coordinate of coordinates) sheet.validations[coordinate] = structuredClone(rule);
    await queueSave();
    closeOverlays();
    renderEditor();
  });
}

async function createFilterFromSelection() {
  document.querySelector(".menu")?.remove();
  const sheet = activeSheet();
  const bounds = selectedBounds(sheet);
  recordHistory();
  sheet.filter = { ...bounds, conditions: {} };
  await queueSave();
  renderEditor();
}

async function clearFilter() {
  document.querySelector(".menu")?.remove();
  const sheet = activeSheet();
  if (!sheet.filter) return;
  recordHistory();
  delete sheet.filter;
  await queueSave();
  renderEditor();
}

function showFilterDialog(column) {
  const sheet = activeSheet();
  const filter = sheet.filter;
  if (!filter) return;
  const header = evaluateCell(sheet, coordinateAt(column, filter.minRow)) || columnLetters(column);
  const values = [];
  for (let row = filter.minRow + 1; row <= filter.maxRow; row += 1) {
    const value = String(evaluateCell(sheet, coordinateAt(column, row)));
    if (!values.includes(value)) values.push(value);
  }
  const existing = filter.conditions?.[column] || {};
  const selected = new Set(existing.selectedValues || values);
  const conditionOptions = [
    { value: "none", label: "No condition" },
    { value: "contains", label: "Text contains" },
    { value: "greater_than", label: "Greater than" },
    { value: "date_before", label: "Date is before" },
    { value: "is_empty", label: "Is empty" },
    { value: "is_not_empty", label: "Is not empty" },
  ];
  const dialog = showDialog(
    `Filter ${header}`,
    `${choiceMarkup(`filter-condition-${column}`, "Condition", conditionOptions, existing.condition || "none")}
     <label for="filter-value-${column}">Value<input id="filter-value-${column}" aria-label="Value" type="text" value="${escapeHtml(existing.value || "")}" /></label>
     <fieldset><legend>Values</legend>
       ${values.map((value, index) => `<label><input type="checkbox" data-filter-value="${escapeHtml(value)}" ${selected.has(value) ? "checked" : ""} /> ${escapeHtml(value || "(Blank)")}</label>`).join("")}
     </fieldset>
     <div class="dialog-actions">
       <button class="secondary" type="button" data-clear-selection>Clear selection</button>
       <button class="secondary" type="button" data-close>Cancel</button>
       <button class="primary" type="button" data-apply>Apply</button>
     </div>`,
  );
  const condition = wireChoice(dialog, `filter-condition-${column}`);
  dialog.querySelector("[data-clear-selection]").addEventListener("click", () => {
    for (const checkbox of dialog.querySelectorAll("[data-filter-value]")) checkbox.checked = false;
  });
  dialog.querySelector("[data-close]").addEventListener("click", closeOverlays);
  dialog.querySelector("[data-apply]").addEventListener("click", async () => {
    const selectedValues = [...dialog.querySelectorAll("[data-filter-value]:checked")].map(
      (checkbox) => checkbox.dataset.filterValue,
    );
    const rule = {};
    if (selectedValues.length !== values.length) rule.selectedValues = selectedValues;
    if (condition.dataset.value !== "none") {
      rule.condition = condition.dataset.value;
      rule.value = dialog.querySelector(`#filter-value-${column}`).value;
    }
    recordHistory();
    filter.conditions ||= {};
    if (Object.keys(rule).length) filter.conditions[column] = rule;
    else delete filter.conditions[column];
    await queueSave();
    closeOverlays();
    renderEditor();
    showFilterRangeConfirmation();
  });
}

function compareSortValues(left, right) {
  const leftNumber = numeric(left);
  const rightNumber = numeric(right);
  if (leftNumber !== null && rightNumber !== null) return leftNumber - rightNumber;
  return String(left).localeCompare(String(right), undefined, { numeric: true, sensitivity: "base" });
}

async function applySort(bounds, sortColumn, direction, hasHeader) {
  const sheet = activeSheet();
  const firstDataRow = bounds.minRow + (hasHeader ? 1 : 0);
  const records = [];
  for (let row = firstDataRow; row <= bounds.maxRow; row += 1) {
    records.push({ row, value: evaluateCell(sheet, coordinateAt(sortColumn, row)) });
  }
  records.sort((left, right) => {
    const comparison = compareSortValues(left.value, right.value);
    return direction === "descending" ? -comparison : comparison;
  });

  recordHistory();
  const originalCells = { ...(sheet.cells || {}) };
  const originalValidations = structuredClone(sheet.validations || {});
  const nextCells = { ...(sheet.cells || {}) };
  const nextValidations = structuredClone(sheet.validations || {});
  records.forEach((record, offset) => {
    const destinationRow = firstDataRow + offset;
    for (let column = bounds.minColumn; column <= bounds.maxColumn; column += 1) {
      const source = coordinateAt(column, record.row);
      const destination = coordinateAt(column, destinationRow);
      const raw = Object.hasOwn(originalCells, source) ? String(originalCells[source]) : "";
      nextCells[destination] = adjustFormula(raw, 0, destinationRow - record.row);
      if (originalValidations[source]) nextValidations[destination] = structuredClone(originalValidations[source]);
      else delete nextValidations[destination];
    }
  });
  sheet.cells = nextCells;
  sheet.validations = nextValidations;
  await queueSave();
  renderEditor();
}

function showSortDialog() {
  const sheet = activeSheet();
  const bounds = selectedBounds(sheet);
  const columns = [];
  for (let column = bounds.minColumn; column <= bounds.maxColumn; column += 1) {
    const label = evaluateCell(sheet, coordinateAt(column, bounds.minRow)) || columnLetters(column);
    columns.push({ value: String(column), label });
  }
  const dialog = showDialog(
    "Sort range",
    `${choiceMarkup("sort-column", "Sort by", columns)}
     ${choiceMarkup("sort-order", "Order", [
       { value: "ascending", label: "Ascending" },
       { value: "descending", label: "Descending" },
     ])}
     <label><input id="sort-header" type="checkbox" /> Data has header row</label>
     <div class="dialog-actions"><button class="secondary" type="button" data-close>Cancel</button><button class="primary" type="button" data-sort>Sort</button></div>`,
  );
  const columnChoice = wireChoice(dialog, "sort-column");
  const orderChoice = wireChoice(dialog, "sort-order");
  dialog.querySelector("[data-close]").addEventListener("click", closeOverlays);
  dialog.querySelector("[data-sort]").addEventListener("click", async () => {
    const sortColumn = Number(columnChoice.dataset.value);
    const direction = orderChoice.dataset.value;
    const hasHeader = dialog.querySelector("#sort-header").checked;
    closeOverlays();
    await applySort(bounds, sortColumn, direction, hasHeader);
  });
}

async function applyPivotConfiguration(sheet, candidate, { updateConfiguration = true } = {}) {
  const result = buildPivotCells(sheet, candidate);
  if (result.error) {
    showMessage(result.error);
    return false;
  }
  recordHistory();
  if (updateConfiguration) Object.assign(sheet.pivot, candidate);
  sheet.cells = result.cells;
  await queueSave();
  renderEditor();
  return true;
}

function showCreatePivotDialog() {
  const source = activeSheet();
  const bounds = selectedBounds(source);
  const start = coordinateAt(bounds.minColumn, bounds.minRow);
  const end = coordinateAt(bounds.maxColumn, bounds.maxRow);
  const dialog = showDialog(
    "Create pivot table",
    `<p>Source range: ${start}:${end}</p>
     <label><input type="radio" name="pivot-destination" value="new" checked /> New worksheet</label>
     <div class="dialog-actions"><button class="secondary" type="button" data-close>Cancel</button><button class="primary" type="button" data-create>Create</button></div>`,
  );
  dialog.querySelector("[data-close]").addEventListener("click", closeOverlays);
  dialog.querySelector("[data-create]").addEventListener("click", async () => {
    let index = 1;
    while (workbook.sheets.some((sheet) => sheet.name === `Pivot${index}`)) index += 1;
    const pivotSheet = {
      id: crypto.randomUUID(),
      name: `Pivot${index}`,
      cells: {},
      validations: {},
      selected: "A1",
      selection: ["A1"],
      pivot: {
        sourceSheetId: source.id,
        range: structuredClone(bounds),
        rowField: "",
        columnField: "",
        valueField: "",
        summary: "SUM",
      },
    };
    workbook.sheets.push(pivotSheet);
    workbook.activeSheetId = pivotSheet.id;
    await queueSave();
    closeOverlays();
    renderEditor();
  });
}

function showFilterRangeConfirmation() {
  document.querySelector(".filter-confirm")?.remove();
  const dialog = document.createElement("section");
  dialog.className = "dialog filter-confirm";
  dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-label", "Filter selected range");
  dialog.innerHTML = `<span>Filter selected range</span><button class="primary" type="button">Apply</button>`;
  dialog.querySelector("button").addEventListener("click", () => dialog.remove());
  document.body.append(dialog);
}

function showDataMenu(button) {
  document.querySelector(".menu")?.remove();
  const rectangle = button.getBoundingClientRect();
  const menu = document.createElement("div");
  menu.className = "menu";
  menu.setAttribute("role", "menu");
  menu.style.left = `${rectangle.left}px`;
  menu.style.top = `${rectangle.bottom + 4}px`;
  menu.innerHTML = `
    <button role="menuitem" type="button" data-data-action="validation">Data validation</button>
    <button role="menuitem" type="button" data-data-action="filter">Create filter</button>
    ${activeSheet().filter ? '<button role="menuitem" type="button" data-data-action="clear-filter">Clear filter</button>' : ""}
    <button role="menuitem" type="button" data-data-action="sort">Sort range</button>
    <button role="menuitem" type="button" data-data-action="pivot">Create pivot table</button>`;
  menu.querySelector('[data-data-action="validation"]').addEventListener("click", showDataValidation);
  menu.querySelector('[data-data-action="filter"]').addEventListener("click", () => void createFilterFromSelection());
  menu.querySelector('[data-data-action="clear-filter"]')?.addEventListener("click", () => void clearFilter());
  menu.querySelector('[data-data-action="sort"]').addEventListener("click", showSortDialog);
  menu.querySelector('[data-data-action="pivot"]').addEventListener("click", showCreatePivotDialog);
  document.body.append(menu);
}

function showDropdownOptions(coordinate, button) {
  document.querySelector(".menu")?.remove();
  const rule = activeSheet().validations?.[coordinate];
  if (!rule || rule.type !== "dropdown") return;
  const rectangle = button.getBoundingClientRect();
  const menu = document.createElement("div");
  menu.className = "menu";
  menu.setAttribute("role", "listbox");
  menu.style.left = `${rectangle.left}px`;
  menu.style.top = `${rectangle.bottom + 2}px`;
  for (const value of rule.values) {
    const option = document.createElement("button");
    option.type = "button";
    option.setAttribute("role", "option");
    option.textContent = value;
    option.addEventListener("click", async () => {
      menu.remove();
      await commitCell(coordinate, value);
    });
    menu.append(option);
  }
  document.body.append(menu);
}

function transformStructuralFormula(raw, axis, index, mode) {
  if (!raw.startsWith("=")) return raw;
  return raw.replace(/(\$?)([A-Z]+)(\$?)(\d+)/gi, (_match, absoluteColumn, letters, absoluteRow, rowText) => {
    let column = columnIndex(letters);
    let row = Number(rowText) - 1;
    const value = axis === "row" ? row : column;
    if (mode === "delete" && value === index) return "#REF!";
    if (mode === "insert" && value >= index) {
      if (axis === "row") row += 1;
      else column += 1;
    } else if (mode === "delete" && value > index) {
      if (axis === "row") row -= 1;
      else column -= 1;
    }
    return `${absoluteColumn ? "$" : ""}${columnLetters(column)}${absoluteRow ? "$" : ""}${row + 1}`;
  });
}

function remapCoordinateMap(values, axis, index, mode, transformValue = (value) => value) {
  const mapped = {};
  for (const [coordinate, value] of Object.entries(values || {})) {
    const parsed = parseCoordinate(coordinate);
    const position = axis === "row" ? parsed.row : parsed.column;
    if (mode === "delete" && position === index) continue;
    if (mode === "insert" && position >= index) {
      if (axis === "row") parsed.row += 1;
      else parsed.column += 1;
    } else if (mode === "delete" && position > index) {
      if (axis === "row") parsed.row -= 1;
      else parsed.column -= 1;
    }
    mapped[coordinateAt(parsed.column, parsed.row)] = transformValue(value);
  }
  return mapped;
}

function adjustDependentPivotRanges(sourceSheetId, axis, index, mode) {
  for (const pivotSheet of workbook.sheets) {
    if (pivotSheet.pivot?.sourceSheetId !== sourceSheetId) continue;
    const range = pivotSheet.pivot.range;
    const minimumKey = axis === "row" ? "minRow" : "minColumn";
    const maximumKey = axis === "row" ? "maxRow" : "maxColumn";
    if (mode === "insert") {
      if (index <= range[minimumKey]) {
        range[minimumKey] += 1;
        range[maximumKey] += 1;
      } else if (index <= range[maximumKey]) {
        range[maximumKey] += 1;
      }
    } else if (index < range[minimumKey]) {
      range[minimumKey] -= 1;
      range[maximumKey] -= 1;
    } else if (index <= range[maximumKey]) {
      range[maximumKey] = Math.max(range[minimumKey], range[maximumKey] - 1);
    }
  }
}

async function changeStructure(axis, index, mode) {
  const sheet = activeSheet();
  recordHistory();
  adjustDependentPivotRanges(sheet.id, axis, index, mode);
  sheet.cells = remapCoordinateMap(sheet.cells, axis, index, mode, (value) =>
    transformStructuralFormula(String(value), axis, index, mode),
  );
  sheet.validations = remapCoordinateMap(sheet.validations, axis, index, mode, (value) =>
    structuredClone(value),
  );
  sheet.selected = "A1";
  sheet.selection = ["A1"];
  await queueSave();
  renderEditor();
}

function showStructureMenu(axis, index, x, y) {
  document.querySelector(".menu")?.remove();
  const noun = axis === "row" ? "row" : "column";
  const before = axis === "row" ? "above" : "left";
  const after = axis === "row" ? "below" : "right";
  const menu = document.createElement("div");
  menu.className = "menu";
  menu.setAttribute("role", "menu");
  menu.style.left = `${x}px`;
  menu.style.top = `${Math.min(y, window.innerHeight - 130)}px`;
  menu.innerHTML = `
    <button role="menuitem" type="button" data-structure="before">Insert 1 ${noun} ${before}</button>
    <button role="menuitem" type="button" data-structure="after">Insert 1 ${noun} ${after}</button>
    <button role="menuitem" type="button" data-structure="delete">Delete ${noun}</button>`;
  menu.querySelector('[data-structure="before"]').addEventListener("click", () =>
    void changeStructure(axis, index, "insert"),
  );
  menu.querySelector('[data-structure="after"]').addEventListener("click", () =>
    void changeStructure(axis, index + 1, "insert"),
  );
  menu.querySelector('[data-structure="delete"]').addEventListener("click", () =>
    void changeStructure(axis, index, "delete"),
  );
  document.body.append(menu);
}

function showWorksheetMenu(sheetId, button) {
  document.querySelector(".menu")?.remove();
  const sheet = workbook.sheets.find((item) => item.id === sheetId);
  const rectangle = button.getBoundingClientRect();
  const menu = document.createElement("div");
  menu.className = "menu";
  menu.setAttribute("role", "menu");
  menu.style.left = `${rectangle.left}px`;
  menu.style.top = `${Math.max(8, rectangle.top - 88)}px`;
  menu.innerHTML = `
    <button role="menuitem" type="button" data-action="rename">Rename</button>
    <button role="menuitem" type="button" data-action="delete">Delete</button>`;
  document.body.append(menu);
  menu.querySelector('[data-action="rename"]').addEventListener("click", () => showRenameWorksheet(sheet));
  menu.querySelector('[data-action="delete"]').addEventListener("click", () => showDeleteWorksheet(sheet));
}

function showRenameWorkbook() {
  const dialog = showDialog(
    "Rename workbook",
    `<label for="workbook-name">Workbook name<input id="workbook-name" type="text" value="${escapeHtml(workbook.name)}" /></label>
     <p class="error" role="alert"></p>
     <div class="dialog-actions"><button class="secondary" type="button" data-close>Cancel</button><button class="primary" type="button" data-save>Save</button></div>`,
  );
  const input = dialog.querySelector("#workbook-name");
  const save = async () => {
    const name = input.value.trim();
    if (!name) {
      dialog.querySelector(".error").textContent = "Workbook name cannot be empty";
      return;
    }
    workbook.name = name;
    await queueSave();
    closeOverlays();
    renderEditor();
  };
  dialog.querySelector("[data-close]").addEventListener("click", closeOverlays);
  dialog.querySelector("[data-save]").addEventListener("click", () => void save());
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void save();
    }
  });
  input.focus();
}

function showRenameWorksheet(sheet) {
  const dialog = showDialog(
    "Rename worksheet",
    `<label for="worksheet-name">Worksheet name<input id="worksheet-name" type="text" value="${escapeHtml(sheet.name)}" /></label>
     <p class="error" role="alert"></p>
     <div class="dialog-actions"><button class="secondary" type="button" data-close>Cancel</button><button class="primary" type="button" data-save>Save</button></div>`,
  );
  const input = dialog.querySelector("#worksheet-name");
  const save = async () => {
    const name = input.value.trim();
    const error = dialog.querySelector(".error");
    if (!name) {
      error.textContent = "Worksheet name cannot be empty";
      return;
    }
    if (workbook.sheets.some((item) => item.id !== sheet.id && item.name === name)) {
      error.textContent = "Worksheet name already exists";
      return;
    }
    sheet.name = name;
    await queueSave();
    closeOverlays();
    renderEditor();
  };
  dialog.querySelector("[data-close]").addEventListener("click", closeOverlays);
  dialog.querySelector("[data-save]").addEventListener("click", () => void save());
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void save();
    }
  });
  input.focus();
}

function showDeleteWorksheet(sheet) {
  document.querySelector(".menu")?.remove();
  if (workbook.sheets.length === 1) {
    showMessage("A workbook must contain at least one worksheet");
    return;
  }
  const dialog = showDialog(
    "Delete worksheet",
    `<p>Delete ${escapeHtml(sheet.name)}?</p>
     <div class="dialog-actions"><button class="secondary" type="button" data-close>Cancel</button><button class="primary" type="button" data-delete>Delete worksheet</button></div>`,
  );
  dialog.querySelector("[data-close]").addEventListener("click", closeOverlays);
  dialog.querySelector("[data-delete]").addEventListener("click", async () => {
    const hasDependentPivot = workbook.sheets.some(
      (candidate) => candidate.pivot?.sourceSheetId === sheet.id,
    );
    if (hasDependentPivot) {
      closeOverlays();
      showMessage("Delete or rebuild dependent pivot tables first");
      return;
    }
    const index = workbook.sheets.indexOf(sheet);
    workbook.sheets.splice(index, 1);
    const next = workbook.sheets[Math.min(index, workbook.sheets.length - 1)];
    workbook.activeSheetId = next.id;
    await queueSave();
    closeOverlays();
    renderEditor();
  });
}

function exportActiveSheet() {
  const sheet = activeSheet();
  const blob = new Blob([sheetCsv(sheet)], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${workbook.name}-${sheet.name}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 0);
}

function wirePivotEditor(sheet) {
  if (!sheet.pivot) return;
  const rows = wireChoice(document, "pivot-rows");
  const columns = wireChoice(document, "pivot-columns");
  const values = wireChoice(document, "pivot-values");
  const summary = wireChoice(document, "pivot-summary");
  document.querySelector("#apply-pivot").addEventListener("click", () => {
    const candidate = {
      rowField: rows.dataset.value,
      columnField: columns.dataset.value,
      valueField: values.dataset.value,
      summary: summary.dataset.value,
    };
    void applyPivotConfiguration(sheet, candidate);
  });
  document.querySelector("#refresh-pivot").addEventListener("click", () => {
    const candidate = {
      rowField: sheet.pivot.rowField,
      columnField: sheet.pivot.columnField,
      valueField: sheet.pivot.valueField,
      summary: sheet.pivot.summary,
    };
    void applyPivotConfiguration(sheet, candidate, { updateConfiguration: false });
  });
}

function wireEditor() {
  const sheet = activeSheet();
  wirePivotEditor(sheet);
  document.querySelector("#rename-workbook").addEventListener("click", showRenameWorkbook);
  document.querySelector("#export-csv").addEventListener("click", exportActiveSheet);
  document.querySelector("#data-menu").addEventListener("click", (event) => {
    event.stopPropagation();
    showDataMenu(event.currentTarget);
  });
  document.querySelector("#undo").addEventListener("click", () => void restoreHistory(undoStack, redoStack));
  document.querySelector("#redo").addEventListener("click", () => void restoreHistory(redoStack, undoStack));
  document.querySelector("#add-sheet").addEventListener("click", async () => {
    let index = 1;
    while (workbook.sheets.some((item) => item.name === `Sheet${index}`)) index += 1;
    const newSheet = {
      id: crypto.randomUUID(),
      name: `Sheet${index}`,
      cells: {},
      validations: {},
      selected: "A1",
      selection: ["A1"],
    };
    workbook.sheets.push(newSheet);
    workbook.activeSheetId = newSheet.id;
    await queueSave();
    renderEditor();
  });
  for (const tab of document.querySelectorAll('[role="tab"][data-sheet-id]')) {
    tab.addEventListener("click", async () => {
      workbook.activeSheetId = tab.dataset.sheetId;
      await queueSave();
      renderEditor();
    });
  }
  for (const button of document.querySelectorAll("[data-sheet-options]")) {
    button.addEventListener("click", () => showWorksheetMenu(button.dataset.sheetOptions, button));
  }
  for (const button of document.querySelectorAll("[data-validation-dropdown]")) {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      showDropdownOptions(button.dataset.validationDropdown, button);
    });
  }
  for (const button of document.querySelectorAll("[data-filter-column]")) {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      showFilterDialog(Number(button.dataset.filterColumn));
    });
  }

  for (const header of document.querySelectorAll("[data-row]")) {
    header.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      showStructureMenu("row", Number(header.dataset.row), event.clientX, event.clientY);
    });
  }
  for (const header of document.querySelectorAll("[data-column]")) {
    header.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      showStructureMenu("column", Number(header.dataset.column), event.clientX, event.clientY);
    });
  }

  const formula = document.querySelector("#formula-bar");
  formula.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      const coordinate = activeSheet().selected || "A1";
      void commitCell(coordinate, formula.value, { resetSelection: true });
    }
  });

  for (const cell of document.querySelectorAll('[role="gridcell"][data-coordinate]')) {
    cell.addEventListener("click", () => {
      if (suppressClick) {
        suppressClick = false;
        return;
      }
      setSingleSelection(cell.dataset.coordinate);
    });
    cell.addEventListener("dblclick", () => startInlineEdit(cell));
    cell.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      setSingleSelection(cell.dataset.coordinate);
      showContextMenu(cell, event.clientX, event.clientY);
    });
    cell.addEventListener("dragstart", (event) => {
      pointerStart = cell.dataset.coordinate;
      pointerLast = pointerStart;
      event.dataTransfer.setData("text/plain", pointerStart);
      event.dataTransfer.effectAllowed = "copy";
    });
    cell.addEventListener("dragover", (event) => event.preventDefault());
    cell.addEventListener("dragenter", (event) => {
      event.preventDefault();
      if (pointerStart) {
        pointerLast = cell.dataset.coordinate;
        setRangeSelection(pointerStart, pointerLast, { persist: false });
      }
    });
    cell.addEventListener("drop", (event) => {
      event.preventDefault();
      if (pointerStart) {
        suppressImmediateDragClick();
        setRangeSelection(pointerStart, cell.dataset.coordinate);
      }
      pointerStart = null;
      pointerLast = null;
    });
    cell.addEventListener("mousedown", (event) => {
      if (event.button === 0) {
        pointerStart = cell.dataset.coordinate;
        pointerLast = pointerStart;
      }
    });
    cell.addEventListener("mouseover", (event) => {
      if (pointerStart && (event.buttons & 1) === 1 && cell.dataset.coordinate !== pointerStart) {
        pointerLast = cell.dataset.coordinate;
        setRangeSelection(pointerStart, pointerLast, { persist: false });
      }
    });
    cell.addEventListener("mouseup", () => {
      if (pointerStart && pointerLast && pointerLast !== pointerStart) {
        suppressImmediateDragClick();
        setRangeSelection(pointerStart, pointerLast);
      }
      pointerStart = null;
      pointerLast = null;
    });
  }
}

document.addEventListener("paste", (event) => {
  if (!workbook || event.target?.matches('[aria-label^="Edit "]')) return;
  event.preventDefault();
  const start = pendingPaste?.start || activeSheet().selected || "A1";
  const textPromise = pendingPaste?.textPromise || clipboardText(event);
  if (pendingPaste) pendingPaste.handled = true;
  pendingPaste = null;
  void enqueuePaste(start, textPromise);
});

document.addEventListener("keydown", (event) => {
  if (!workbook || event.target?.matches('[aria-label^="Edit "]')) return;
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
    event.preventDefault();
    void restoreHistory(event.shiftKey ? redoStack : undoStack, event.shiftKey ? undoStack : redoStack);
  } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") {
    event.preventDefault();
    void restoreHistory(redoStack, undoStack);
  } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "v") {
    const immediate = internalClipboard?.text;
    const operation = {
      start: activeSheet().selected || "A1",
      handled: false,
      textPromise: immediate ? Promise.resolve(immediate) : navigator.clipboard.readText(),
    };
    pendingPaste = operation;
    setTimeout(() => {
      if (operation.handled) return;
      operation.handled = true;
      if (pendingPaste === operation) pendingPaste = null;
      void enqueuePaste(operation.start, operation.textPromise);
    }, 0);
  } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "c") {
    event.preventDefault();
    void copySelection(false);
  } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "x") {
    event.preventDefault();
    void copySelection(true);
  }
});

document.addEventListener("click", (event) => {
  if (!event.target.closest(".menu") && !event.target.closest("[data-sheet-options]")) {
    document.querySelector(".menu")?.remove();
  }
});

async function boot() {
  try {
    const match = /^\/workbooks\/([^/]+)\/?$/.exec(window.location.pathname);
    if (!match) {
      await renderHome();
      return;
    }
    workbook = await request(`/api/workbooks/${decodeURIComponent(match[1])}`);
    undoStack = [];
    redoStack = [];
    for (const sheet of workbook.sheets) {
      sheet.cells ||= {};
      sheet.validations ||= {};
      sheet.selected ||= "A1";
      sheet.selection ||= [sheet.selected];
    }
    renderEditor();
  } catch (error) {
    app.innerHTML = `<main class="home"><h1>Unable to open workbook</h1><p role="alert">${escapeHtml(error.message)}</p><a href="/">Back to workbooks</a></main>`;
  }
}

void boot();
