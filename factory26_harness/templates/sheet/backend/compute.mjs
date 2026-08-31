import { createHash, randomUUID } from "node:crypto";

const FIELD_TYPES = new Set(["string", "number", "boolean", "date", "enum", "reference", "formula"]);
const ACCOUNT_TYPES = new Set(["asset", "liability", "equity", "revenue", "expense"]);
const ITEM_TYPES = new Set(["purchased", "manufactured"]);

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function clean(value, maximum = 300) {
  return String(value ?? "").trim().slice(0, maximum);
}

function roundQuantity(value) {
  return Math.round((Number(value) + Number.EPSILON) * 1_000_000) / 1_000_000;
}

function nonnegative(value, label) {
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) throw new Error(`${label} must be a non-negative number`);
  return roundQuantity(number);
}

function integer(value, label, maximum = 3650) {
  const number = Number(value);
  if (!Number.isInteger(number) || number < 0 || number > maximum) throw new Error(`${label} must be an integer from 0 to ${maximum}`);
  return number;
}

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  return JSON.stringify(value);
}

function hash(value) {
  return createHash("sha256").update(canonical(value)).digest("hex");
}

function computeBusinessStateHash(enterprise) {
  return hash({
    schemas: enterprise.schemas,
    records: enterprise.records,
    ledger: enterprise.ledger,
    mrp: enterprise.mrp,
  });
}

function fail(code, message, details = undefined) {
  return { ok: false, code, message, ...(details ? { details } : {}) };
}

export function normalizeComputeState(workbook) {
  workbook.enterprise ||= {};
  const enterprise = workbook.enterprise;
  if (!Array.isArray(enterprise.schemas)) enterprise.schemas = [];
  if (!enterprise.records || typeof enterprise.records !== "object" || Array.isArray(enterprise.records)) enterprise.records = {};
  enterprise.ledger ||= {};
  if (!Array.isArray(enterprise.ledger.accounts)) enterprise.ledger.accounts = [];
  if (!Array.isArray(enterprise.ledger.journals)) enterprise.ledger.journals = [];
  if (!Array.isArray(enterprise.ledger.closedPeriods)) enterprise.ledger.closedPeriods = [];
  if (!Array.isArray(enterprise.ledger.idempotency)) enterprise.ledger.idempotency = [];
  enterprise.mrp ||= {};
  if (!Array.isArray(enterprise.mrp.items)) enterprise.mrp.items = [];
  if (!Array.isArray(enterprise.mrp.bom)) enterprise.mrp.bom = [];
  if (!Array.isArray(enterprise.mrp.demands)) enterprise.mrp.demands = [];
  if (!Array.isArray(enterprise.mrp.receipts)) enterprise.mrp.receipts = [];
  if (!Array.isArray(enterprise.mrp.runs)) enterprise.mrp.runs = [];
  if (!Array.isArray(enterprise.computeEvents)) enterprise.computeEvents = [];
  enterprise.version = 2;
  if (!Number.isInteger(enterprise.revision) || enterprise.revision < 0) enterprise.revision = 0;
  return workbook;
}

function tokenize(expression) {
  const tokens = [];
  let index = 0;
  while (index < expression.length) {
    const rest = expression.slice(index);
    const whitespace = /^\s+/.exec(rest);
    if (whitespace) {
      index += whitespace[0].length;
      continue;
    }
    const number = /^(?:\d+(?:\.\d+)?|\.\d+)/.exec(rest);
    if (number) {
      tokens.push({ type: "number", value: Number(number[0]) });
      index += number[0].length;
      continue;
    }
    const identifier = /^[A-Za-z_][A-Za-z0-9_]*/.exec(rest);
    if (identifier) {
      tokens.push({ type: "identifier", value: identifier[0] });
      index += identifier[0].length;
      continue;
    }
    const operator = rest[0];
    if ("+-*/()".includes(operator)) {
      tokens.push({ type: operator, value: operator });
      index += 1;
      continue;
    }
    throw new Error(`unsupported formula token at position ${index + 1}`);
  }
  return tokens;
}

export function evaluateRuntimeFormula(expression, values) {
  const tokens = tokenize(clean(expression, 500));
  let position = 0;
  function primary() {
    const token = tokens[position];
    if (!token) throw new Error("formula ended unexpectedly");
    if (token.type === "number") {
      position += 1;
      return token.value;
    }
    if (token.type === "identifier") {
      position += 1;
      const value = Number(values[token.value]);
      if (!Number.isFinite(value)) throw new Error(`formula field is not numeric: ${token.value}`);
      return value;
    }
    if (token.type === "(") {
      position += 1;
      const value = addition();
      if (tokens[position]?.type !== ")") throw new Error("formula is missing a closing parenthesis");
      position += 1;
      return value;
    }
    if (token.type === "+" || token.type === "-") {
      position += 1;
      const value = primary();
      return token.type === "-" ? -value : value;
    }
    throw new Error(`unexpected formula token: ${token.value}`);
  }
  function multiplication() {
    let value = primary();
    while (["*", "/"].includes(tokens[position]?.type)) {
      const operator = tokens[position].type;
      position += 1;
      const right = primary();
      if (operator === "/" && right === 0) throw new Error("formula division by zero");
      value = operator === "*" ? value * right : value / right;
    }
    return value;
  }
  function addition() {
    let value = multiplication();
    while (["+", "-"].includes(tokens[position]?.type)) {
      const operator = tokens[position].type;
      position += 1;
      const right = multiplication();
      value = operator === "+" ? value + right : value - right;
    }
    return value;
  }
  if (!tokens.length) throw new Error("formula is required");
  const result = addition();
  if (position !== tokens.length) throw new Error(`unexpected formula token: ${tokens[position].value}`);
  if (!Number.isFinite(result)) throw new Error("formula result is not finite");
  return roundQuantity(result);
}

function formulaOrder(fields) {
  const byId = new Map(fields.map((field) => [field.id, field]));
  const formulaFields = fields.filter((field) => field.type === "formula");
  const dependencies = new Map();
  for (const field of formulaFields) {
    const identifiers = [...new Set(tokenize(field.expression)
      .filter((token) => token.type === "identifier")
      .map((token) => token.value))];
    for (const identifier of identifiers) {
      const dependency = byId.get(identifier);
      if (!dependency) throw new Error(`formula field ${field.id} references an unknown field: ${identifier}`);
      if (!["number", "formula"].includes(dependency.type)) throw new Error(`formula field ${field.id} requires a numeric field: ${identifier}`);
    }
    dependencies.set(field.id, identifiers.filter((identifier) => byId.get(identifier)?.type === "formula"));
  }
  const ordered = [];
  const visiting = new Set();
  const visited = new Set();
  function visit(fieldId, path) {
    if (visiting.has(fieldId)) throw new Error(`formula cycle detected: ${[...path, fieldId].join(" -> ")}`);
    if (visited.has(fieldId)) return;
    visiting.add(fieldId);
    for (const dependency of dependencies.get(fieldId) || []) visit(dependency, [...path, fieldId]);
    visiting.delete(fieldId);
    visited.add(fieldId);
    ordered.push(byId.get(fieldId));
  }
  for (const field of formulaFields) visit(field.id, []);
  return ordered;
}

function normalizeFields(fields) {
  const ids = new Set();
  const normalized = asArray(fields).map((raw) => {
    const id = clean(raw.id, 80);
    const type = clean(raw.type || "string", 40).toLowerCase();
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(id)) throw new Error(`invalid field id: ${id || "<empty>"}`);
    if (ids.has(id)) throw new Error(`duplicate field id: ${id}`);
    if (!FIELD_TYPES.has(type)) throw new Error(`unsupported field type: ${type}`);
    ids.add(id);
    const field = {
      id,
      label: clean(raw.label || id, 160),
      type,
      required: Boolean(raw.required),
      unique: Boolean(raw.unique),
    };
    if (type === "enum") {
      field.options = [...new Set(asArray(raw.options).map((entry) => clean(entry, 160)).filter(Boolean))];
      if (!field.options.length) throw new Error(`enum field ${id} requires options`);
    }
    if (type === "reference") {
      field.referenceSchemaId = clean(raw.referenceSchemaId, 160);
      if (!field.referenceSchemaId) throw new Error(`reference field ${id} requires a target schema`);
    }
    if (type === "formula") {
      field.expression = clean(raw.expression, 500);
      if (!field.expression) throw new Error(`formula field ${id} requires an expression`);
    }
    return field;
  });
  formulaOrder(normalized);
  return normalized;
}

function isoDate(value, label) {
  const text = clean(value, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) throw new Error(`${label} must be YYYY-MM-DD`);
  const date = new Date(`${text}T00:00:00.000Z`);
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== text) throw new Error(`${label} is not a valid calendar date`);
  return text;
}

function validateRecord(enterprise, schema, rawValues, recordId = "") {
  const values = {};
  for (const field of schema.fields) {
    let value = rawValues?.[field.id];
    if (field.type === "formula") continue;
    if ((value === undefined || value === null || value === "") && field.required) throw new Error(`${field.label} is required`);
    if (value === undefined || value === null || value === "") {
      values[field.id] = "";
      continue;
    }
    if (field.type === "number") {
      value = Number(value);
      if (!Number.isFinite(value)) throw new Error(`${field.label} must be numeric`);
      value = roundQuantity(value);
    } else if (field.type === "boolean") {
      value = value === true || value === "true";
    } else if (field.type === "date") {
      value = isoDate(value, field.label);
    } else if (field.type === "enum") {
      value = clean(value, 160);
      if (!field.options.includes(value)) throw new Error(`${field.label} must be one of: ${field.options.join(", ")}`);
    } else if (field.type === "reference") {
      value = clean(value, 160);
      const references = asArray(enterprise.records[field.referenceSchemaId]);
      if (!references.some((entry) => entry.id === value)) throw new Error(`${field.label} references an unknown record`);
    } else {
      value = clean(value, 10_000);
    }
    values[field.id] = value;
  }
  for (const field of schema.fields.filter((entry) => entry.unique && entry.type !== "formula")) {
    const duplicate = asArray(enterprise.records[schema.id]).find((entry) => entry.id !== recordId && entry.values?.[field.id] === values[field.id]);
    if (duplicate) throw new Error(`${field.label} must be unique`);
  }
  for (const field of formulaOrder(schema.fields)) values[field.id] = evaluateRuntimeFormula(field.expression, values);
  return values;
}

function moneyToCents(value, label) {
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount < 0) throw new Error(`${label} must be a non-negative amount`);
  const cents = Math.round(amount * 100);
  if (Math.abs(amount * 100 - cents) > 1e-7) throw new Error(`${label} supports at most two decimal places`);
  return cents;
}

function centsToMoney(value) {
  return Math.round(value) / 100;
}

function postJournal(enterprise, raw, actor, reversalOf = "") {
  const lines = asArray(raw.lines).map((line) => ({
    accountCode: clean(line.accountCode, 80),
    memo: clean(line.memo, 300),
    debitCents: moneyToCents(line.debit || 0, "debit"),
    creditCents: moneyToCents(line.credit || 0, "credit"),
  }));
  if (lines.length < 2) throw new Error("a journal entry requires at least two lines");
  for (const line of lines) {
    const account = enterprise.ledger.accounts.find((entry) => entry.code === line.accountCode);
    if (!account) throw new Error(`unknown ledger account: ${line.accountCode}`);
    if (!account.active) throw new Error(`ledger account is inactive: ${line.accountCode}`);
    if ((line.debitCents > 0) === (line.creditCents > 0)) throw new Error("each journal line must contain either a debit or a credit");
  }
  const debitCents = lines.reduce((sum, line) => sum + line.debitCents, 0);
  const creditCents = lines.reduce((sum, line) => sum + line.creditCents, 0);
  if (debitCents !== creditCents) throw new Error(`journal entry is not balanced: debit ${centsToMoney(debitCents)} != credit ${centsToMoney(creditCents)}`);
  const date = isoDate(raw.date || new Date().toISOString().slice(0, 10), "journal date");
  if (enterprise.ledger.closedPeriods.includes(date.slice(0, 7))) throw new Error(`accounting period is closed: ${date.slice(0, 7)}`);
  const currency = clean(raw.currency || "CNY", 8).toUpperCase();
  const accountCurrencies = new Set(lines.map((line) => enterprise.ledger.accounts.find((account) => account.code === line.accountCode)?.currency));
  if (accountCurrencies.size !== 1 || !accountCurrencies.has(currency)) throw new Error("journal currency must match every account currency");
  const sequence = enterprise.ledger.journals.length + 1;
  const item = {
    id: randomUUID(),
    sequence,
    reference: clean(raw.reference || `JE-${String(sequence).padStart(5, "0")}`, 120),
    date,
    memo: clean(raw.memo, 500),
    currency,
    status: "posted",
    actor,
    postedAt: new Date().toISOString(),
    reversalOf,
    lines,
    debit: centsToMoney(debitCents),
    credit: centsToMoney(creditCents),
  };
  item.hash = hash(item);
  enterprise.ledger.journals.push(item);
  return item;
}

export function trialBalance(enterprise) {
  const rows = enterprise.ledger.accounts.map((account) => {
    const lines = enterprise.ledger.journals.flatMap((journal) => journal.lines.filter((line) => line.accountCode === account.code));
    const debitCents = lines.reduce((sum, line) => sum + line.debitCents, 0);
    const creditCents = lines.reduce((sum, line) => sum + line.creditCents, 0);
    return {
      code: account.code,
      name: account.name,
      type: account.type,
      debit: centsToMoney(debitCents),
      credit: centsToMoney(creditCents),
      balance: centsToMoney(debitCents - creditCents),
    };
  });
  const debit = centsToMoney(rows.reduce((sum, row) => sum + moneyToCents(row.debit, "debit"), 0));
  const credit = centsToMoney(rows.reduce((sum, row) => sum + moneyToCents(row.credit, "credit"), 0));
  return { rows, debit, credit, balanced: debit === credit };
}

function assertBomAcyclic(mrp) {
  const graph = new Map();
  for (const line of mrp.bom) {
    const children = graph.get(line.parentId) || [];
    children.push(line.componentId);
    graph.set(line.parentId, children);
  }
  const visiting = new Set();
  const visited = new Set();
  function visit(itemId, path) {
    if (visiting.has(itemId)) throw new Error(`BOM cycle detected: ${[...path, itemId].join(" -> ")}`);
    if (visited.has(itemId)) return;
    visiting.add(itemId);
    for (const child of graph.get(itemId) || []) visit(child, [...path, itemId]);
    visiting.delete(itemId);
    visited.add(itemId);
  }
  for (const item of mrp.items) visit(item.id, []);
}

function subtractDays(date, days) {
  const value = new Date(`${date}T00:00:00.000Z`);
  value.setUTCDate(value.getUTCDate() - days);
  return value.toISOString().slice(0, 10);
}

export function runMrp(mrp, asOfDate = new Date().toISOString().slice(0, 10)) {
  assertBomAcyclic(mrp);
  const byId = new Map(mrp.items.map((item) => [item.id, item]));
  const inventory = new Map(mrp.items.map((item) => [item.id, roundQuantity(item.onHand + item.scheduledReceipts)]));
  const receiptsByItem = new Map();
  for (const receipt of asArray(mrp.receipts)) {
    const entries = receiptsByItem.get(receipt.itemId) || [];
    entries.push(receipt);
    receiptsByItem.set(receipt.itemId, entries);
  }
  for (const entries of receiptsByItem.values()) entries.sort((left, right) => left.dueDate.localeCompare(right.dueDate) || left.id.localeCompare(right.id));
  const appliedReceipts = new Set();
  const queue = mrp.demands.map((demand) => ({ itemId: demand.itemId, quantity: demand.quantity, dueDate: demand.dueDate, source: demand.id, level: 0 }));
  const rows = [];
  let safetyCounter = 0;
  while (queue.length) {
    if (safetyCounter++ > 10_000) throw new Error("MRP explosion exceeded 10,000 requirement events");
    queue.sort((left, right) => left.dueDate.localeCompare(right.dueDate) || left.level - right.level || left.itemId.localeCompare(right.itemId));
    const event = queue.shift();
    const item = byId.get(event.itemId);
    if (!item) throw new Error(`demand references unknown item: ${event.itemId}`);
    let scheduledReceiptsApplied = 0;
    for (const receipt of receiptsByItem.get(item.id) || []) {
      if (!appliedReceipts.has(receipt.id) && receipt.dueDate <= event.dueDate) {
        scheduledReceiptsApplied = roundQuantity(scheduledReceiptsApplied + receipt.quantity);
        appliedReceipts.add(receipt.id);
      }
    }
    if (scheduledReceiptsApplied) inventory.set(item.id, roundQuantity((inventory.get(item.id) || 0) + scheduledReceiptsApplied));
    const availableBefore = inventory.get(item.id) || 0;
    const usable = Math.max(0, availableBefore - item.safetyStock);
    const netRequirement = Math.max(0, roundQuantity(event.quantity - usable));
    const plannedOrder = netRequirement > 0 ? roundQuantity(Math.ceil(netRequirement / item.lotSize) * item.lotSize) : 0;
    const availableAfter = roundQuantity(availableBefore + plannedOrder - event.quantity);
    inventory.set(item.id, availableAfter);
    const releaseDate = subtractDays(event.dueDate, item.leadTimeDays);
    rows.push({
      itemId: item.id,
      itemName: item.name,
      itemType: item.type,
      level: event.level,
      source: event.source,
      dueDate: event.dueDate,
      releaseDate,
      grossRequirement: event.quantity,
      scheduledReceiptsApplied,
      availableBefore,
      safetyStock: item.safetyStock,
      netRequirement,
      plannedOrder,
      projectedAvailable: availableAfter,
      late: releaseDate < asOfDate,
    });
    if (plannedOrder > 0) {
      for (const line of mrp.bom.filter((entry) => entry.parentId === item.id)) {
        queue.push({
          itemId: line.componentId,
          quantity: roundQuantity(plannedOrder * line.quantity * (1 + line.scrapRate)),
          dueDate: releaseDate,
          source: `${item.id}:${event.source}`,
          level: event.level + 1,
        });
      }
    }
  }
  return rows;
}

function recordComputeEvent(enterprise, actor, action, payload, result) {
  const previous = enterprise.computeEvents.at(-1);
  const event = {
    id: randomUUID(),
    sequence: (previous?.sequence || 0) + 1,
    timestamp: new Date().toISOString(),
    actor,
    action,
    resourceId: clean(result?.id || result?.code || result?.reference || "", 200),
    inputHash: hash(payload),
    outputHash: hash(result),
    stateHash: computeBusinessStateHash(enterprise),
    previousHash: previous?.hash || "GENESIS",
  };
  event.hash = hash(event);
  enterprise.computeEvents.push(event);
}

export function verifyComputeEvents(events) {
  let previousHash = "GENESIS";
  for (let index = 0; index < asArray(events).length; index += 1) {
    const event = events[index];
    if (event.sequence !== index + 1 || event.previousHash !== previousHash) {
      return { valid: false, brokenAt: index + 1, reason: "sequence_or_link_mismatch" };
    }
    const { hash: eventHash, ...unsigned } = event;
    if (hash(unsigned) !== eventHash) return { valid: false, brokenAt: index + 1, reason: "event_hash_mismatch" };
    previousHash = eventHash;
  }
  return { valid: true, count: asArray(events).length, headHash: previousHash };
}

export function verifyComputeState(enterprise) {
  const events = verifyComputeEvents(enterprise?.computeEvents);
  if (!events.valid) return { valid: false, layer: "compute_events", ...events };
  const journals = asArray(enterprise?.ledger?.journals);
  const journalIds = new Set(journals.map((journal) => journal.id));
  const closedPeriods = asArray(enterprise?.ledger?.closedPeriods);
  if (new Set(closedPeriods).size !== closedPeriods.length || closedPeriods.some((period) => !/^\d{4}-(0[1-9]|1[0-2])$/.test(period))) {
    return { valid: false, layer: "ledger", reason: "closed_periods_invalid" };
  }
  for (let index = 0; index < journals.length; index += 1) {
    const journal = journals[index];
    const { hash: journalHash, ...unsigned } = journal;
    if (journal.sequence !== index + 1 || hash(unsigned) !== journalHash) {
      return { valid: false, layer: "ledger", brokenAt: index + 1, reason: "journal_hash_mismatch" };
    }
    if (journal.reversalOf && !journalIds.has(journal.reversalOf)) {
      return { valid: false, layer: "ledger", brokenAt: index + 1, reason: "reversal_target_missing" };
    }
  }
  const idempotencyKeys = new Set();
  for (const record of asArray(enterprise?.ledger?.idempotency)) {
    if (!record.key || idempotencyKeys.has(record.key) || !journalIds.has(record.journalId) || !/^[a-f0-9]{64}$/.test(record.inputHash || "")) {
      return { valid: false, layer: "ledger", reason: "idempotency_index_invalid" };
    }
    idempotencyKeys.add(record.key);
  }
  const itemIds = new Set(asArray(enterprise?.mrp?.items).map((item) => item.id));
  for (const receipt of asArray(enterprise?.mrp?.receipts)) {
    if (!receipt.id || !itemIds.has(receipt.itemId) || !/^\d{4}-\d{2}-\d{2}$/.test(receipt.dueDate || "") || !Number.isFinite(receipt.quantity) || receipt.quantity <= 0) {
      return { valid: false, layer: "mrp", reason: "scheduled_receipt_invalid" };
    }
  }
  const balance = trialBalance(enterprise);
  if (!balance.balanced) return { valid: false, layer: "ledger", reason: "trial_balance_mismatch" };
  if (events.count > 0) {
    const expectedStateHash = enterprise.computeEvents.at(-1)?.stateHash;
    if (!/^[a-f0-9]{64}$/.test(expectedStateHash || "")) {
      return { valid: false, layer: "business_state", reason: "state_hash_missing" };
    }
    const actualStateHash = computeBusinessStateHash(enterprise);
    if (actualStateHash !== expectedStateHash) {
      return {
        valid: false,
        layer: "business_state",
        reason: "state_hash_mismatch",
        expectedStateHash,
        actualStateHash,
      };
    }
  }
  return {
    valid: true,
    events,
    journals: { valid: true, count: journals.length },
    headHash: events.headHash,
    stateBound: events.count > 0,
    stateHash: events.count > 0 ? enterprise.computeEvents.at(-1).stateHash : computeBusinessStateHash(enterprise),
  };
}

export function executeComputeCommand(workbook, command, context = {}) {
  normalizeComputeState(workbook);
  const enterprise = workbook.enterprise;
  const { type, payload = {} } = command || {};
  const actor = clean(context.actor || "local-user", 160);
  const integrity = verifyComputeState(enterprise);
  if (type === "compute.verify") return { ok: true, item: integrity };
  if (!integrity.valid) return fail("integrity", `enterprise state integrity failed: ${integrity.layer || integrity.reason}`, integrity);
  let result;
  try {
    if (type === "schema.upsert") {
      const raw = payload.item || payload;
      const id = clean(raw.id || clean(raw.name, 120).toLowerCase().replace(/[^a-z0-9]+/g, "-"), 160);
      if (!/^[a-z][a-z0-9-]*$/.test(id)) throw new Error("schema id must start with a letter and contain lowercase letters, numbers, or hyphens");
      const existing = enterprise.schemas.find((entry) => entry.id === id);
      const fields = normalizeFields(raw.fields);
      for (const field of fields.filter((entry) => entry.type === "reference")) if (!enterprise.schemas.some((entry) => entry.id === field.referenceSchemaId) && field.referenceSchemaId !== id) throw new Error(`reference schema not found: ${field.referenceSchemaId}`);
      const item = { id, name: clean(raw.name || id, 160), fields, version: (existing?.version || 0) + 1, updatedAt: new Date().toISOString() };
      const migratedRecords = asArray(enterprise.records[id]).map((record) => ({
        ...record,
        values: validateRecord(enterprise, item, record.values || {}, record.id),
        updatedAt: new Date().toISOString(),
      }));
      for (const field of fields.filter((entry) => entry.unique && entry.type !== "formula")) {
        const seen = new Set();
        for (const record of migratedRecords) {
          const value = canonical(record.values[field.id]);
          if (seen.has(value)) throw new Error(`${field.label} must remain unique after schema migration`);
          seen.add(value);
        }
      }
      if (existing) Object.assign(existing, item);
      else enterprise.schemas.push(item);
      enterprise.records[id] = migratedRecords;
      result = { ok: true, item: existing || item };
    } else if (type === "schema.record.upsert") {
      const schema = enterprise.schemas.find((entry) => entry.id === payload.schemaId);
      if (!schema) throw new Error("schema not found");
      const records = (enterprise.records[schema.id] ||= []);
      const existing = payload.id ? records.find((entry) => entry.id === payload.id) : null;
      const id = clean(payload.id || randomUUID(), 160);
      const values = validateRecord(enterprise, schema, payload.values || {}, id);
      const item = { id, schemaId: schema.id, values, updatedAt: new Date().toISOString() };
      if (existing) Object.assign(existing, item);
      else records.push(item);
      result = { ok: true, item: existing || item };
    } else if (type === "ledger.account.upsert") {
      const code = clean(payload.code, 80);
      const accountType = clean(payload.accountType || payload.type, 40).toLowerCase();
      if (!/^[A-Za-z0-9._-]+$/.test(code)) throw new Error("account code is required and contains invalid characters");
      if (!ACCOUNT_TYPES.has(accountType)) throw new Error("account type is invalid");
      const existing = enterprise.ledger.accounts.find((entry) => entry.code === code);
      const item = { code, name: clean(payload.name || code, 160), type: accountType, currency: clean(payload.currency || "CNY", 8).toUpperCase(), active: payload.active !== false };
      if (existing) Object.assign(existing, item);
      else enterprise.ledger.accounts.push(item);
      result = { ok: true, item: existing || item };
    } else if (type === "ledger.journal.post") {
      const idempotencyKey = clean(payload.idempotencyKey || payload.reference, 120);
      const inputHash = hash({ ...payload, idempotencyKey });
      const existingRequest = idempotencyKey && enterprise.ledger.idempotency.find((entry) => entry.key === idempotencyKey);
      if (existingRequest) {
        if (existingRequest.inputHash !== inputHash) return fail("idempotency_conflict", `journal request key was already used with different input: ${idempotencyKey}`);
        const existingJournal = enterprise.ledger.journals.find((entry) => entry.id === existingRequest.journalId);
        if (!existingJournal) return fail("integrity", "idempotency index references a missing journal");
        result = { ok: true, item: existingJournal, replayed: true };
      } else {
        const item = postJournal(enterprise, payload, actor);
        if (idempotencyKey) enterprise.ledger.idempotency.push({ key: idempotencyKey, inputHash, journalId: item.id, createdAt: new Date().toISOString() });
        result = { ok: true, item };
      }
    } else if (type === "ledger.journal.reverse") {
      const original = enterprise.ledger.journals.find((entry) => entry.id === payload.id);
      if (!original) throw new Error("journal entry not found");
      if (enterprise.ledger.journals.some((entry) => entry.reversalOf === original.id)) throw new Error("journal entry has already been reversed");
      result = { ok: true, item: postJournal(enterprise, { date: payload.date, memo: `Reversal: ${original.memo}`, reference: `REV-${original.reference}`, currency: original.currency, lines: original.lines.map((line) => ({ accountCode: line.accountCode, debit: centsToMoney(line.creditCents), credit: centsToMoney(line.debitCents), memo: line.memo })) }, actor, original.id) };
    } else if (type === "ledger.trial_balance") {
      result = { ok: true, item: trialBalance(enterprise) };
    } else if (type === "ledger.period.close") {
      const period = clean(payload.period, 7);
      if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(period)) throw new Error("accounting period must use YYYY-MM");
      if (enterprise.ledger.closedPeriods.includes(period)) throw new Error(`accounting period is already closed: ${period}`);
      enterprise.ledger.closedPeriods.push(period);
      enterprise.ledger.closedPeriods.sort();
      result = { ok: true, item: { period, status: "closed", actor, closedAt: new Date().toISOString() } };
    } else if (type === "ledger.period.reopen") {
      const period = clean(payload.period, 7);
      if (payload.confirmPeriod !== period) throw new Error("type the accounting period to confirm reopening");
      if (!enterprise.ledger.closedPeriods.includes(period)) throw new Error(`accounting period is not closed: ${period}`);
      enterprise.ledger.closedPeriods = enterprise.ledger.closedPeriods.filter((entry) => entry !== period);
      result = { ok: true, item: { period, status: "open", actor, reopenedAt: new Date().toISOString() } };
    } else if (type === "mrp.item.upsert") {
      const id = clean(payload.id, 100);
      const itemType = clean(payload.itemType || payload.type || "purchased", 40).toLowerCase();
      if (!/^[A-Za-z0-9._-]+$/.test(id)) throw new Error("item id is required and contains invalid characters");
      if (!ITEM_TYPES.has(itemType)) throw new Error("item type must be purchased or manufactured");
      const existing = enterprise.mrp.items.find((entry) => entry.id === id);
      const item = { id, name: clean(payload.name || id, 160), type: itemType, onHand: nonnegative(payload.onHand || 0, "on-hand quantity"), scheduledReceipts: nonnegative(payload.scheduledReceipts || 0, "scheduled receipts"), safetyStock: nonnegative(payload.safetyStock || 0, "safety stock"), leadTimeDays: integer(payload.leadTimeDays || 0, "lead time"), lotSize: Math.max(0.000001, nonnegative(payload.lotSize || 1, "lot size")) };
      if (existing) Object.assign(existing, item);
      else enterprise.mrp.items.push(item);
      result = { ok: true, item: existing || item };
    } else if (type === "mrp.bom.upsert") {
      const parentId = clean(payload.parentId, 100);
      const componentId = clean(payload.componentId, 100);
      if (parentId === componentId) throw new Error("a BOM item cannot contain itself");
      if (!enterprise.mrp.items.some((entry) => entry.id === parentId) || !enterprise.mrp.items.some((entry) => entry.id === componentId)) throw new Error("BOM parent and component must both exist");
      const id = `${parentId}:${componentId}`;
      const existing = enterprise.mrp.bom.find((entry) => entry.id === id);
      const previous = existing ? structuredClone(existing) : null;
      const item = { id, parentId, componentId, quantity: Math.max(0.000001, nonnegative(payload.quantity, "component quantity")), scrapRate: nonnegative(payload.scrapRate || 0, "scrap rate") };
      if (item.scrapRate > 1) throw new Error("scrap rate must be between 0 and 1");
      if (existing) Object.assign(existing, item);
      else enterprise.mrp.bom.push(item);
      try {
        assertBomAcyclic(enterprise.mrp);
      } catch (error) {
        if (existing) Object.assign(existing, previous);
        else enterprise.mrp.bom = enterprise.mrp.bom.filter((entry) => entry.id !== id);
        throw error;
      }
      result = { ok: true, item: existing || item };
    } else if (type === "mrp.demand.upsert") {
      const itemId = clean(payload.itemId, 100);
      if (!enterprise.mrp.items.some((entry) => entry.id === itemId)) throw new Error("demand item not found");
      const dueDate = isoDate(payload.dueDate, "due date");
      const id = clean(payload.id || randomUUID(), 160);
      const existing = enterprise.mrp.demands.find((entry) => entry.id === id);
      const item = { id, itemId, quantity: Math.max(0.000001, nonnegative(payload.quantity, "demand quantity")), dueDate, reference: clean(payload.reference, 160) };
      if (existing) Object.assign(existing, item);
      else enterprise.mrp.demands.push(item);
      result = { ok: true, item: existing || item };
    } else if (type === "mrp.receipt.upsert") {
      const itemId = clean(payload.itemId, 100);
      if (!enterprise.mrp.items.some((entry) => entry.id === itemId)) throw new Error("scheduled receipt item not found");
      const dueDate = isoDate(payload.dueDate, "scheduled receipt date");
      const id = clean(payload.id || randomUUID(), 160);
      const existing = enterprise.mrp.receipts.find((entry) => entry.id === id);
      const item = { id, itemId, quantity: Math.max(0.000001, nonnegative(payload.quantity, "scheduled receipt quantity")), dueDate, reference: clean(payload.reference, 160) };
      if (existing) Object.assign(existing, item);
      else enterprise.mrp.receipts.push(item);
      result = { ok: true, item: existing || item };
    } else if (type === "mrp.run") {
      const asOfDate = isoDate(payload.asOfDate || new Date().toISOString().slice(0, 10), "as-of date");
      const rows = runMrp(enterprise.mrp, asOfDate);
      const item = { id: randomUUID(), asOfDate, createdAt: new Date().toISOString(), inputHash: hash({ items: enterprise.mrp.items, bom: enterprise.mrp.bom, demands: enterprise.mrp.demands, receipts: enterprise.mrp.receipts }), rows };
      item.outputHash = hash(rows);
      enterprise.mrp.runs.push(item);
      result = { ok: true, item };
    } else {
      return null;
    }
    if (result.ok && !result.replayed && !["compute.verify", "ledger.trial_balance"].includes(type)) recordComputeEvent(enterprise, actor, type, payload, result.item);
    return result;
  } catch (error) {
    return fail("validation", error.message);
  }
}
