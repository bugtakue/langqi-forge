import assert from "node:assert/strict";
import test from "node:test";
import { pathToFileURL } from "node:url";

const computeModule = process.env.COMPUTE_MODULE
  ? pathToFileURL(process.env.COMPUTE_MODULE).href
  : new URL("../factory26_harness/templates/sheet/backend/compute.mjs", import.meta.url).href;
const {
  evaluateRuntimeFormula,
  executeComputeCommand,
  normalizeComputeState,
  runMrp,
  trialBalance,
  verifyComputeState,
} = await import(computeModule);

function workbookFixture() {
  return normalizeComputeState({
    id: "workbook-1",
    name: "Factory control tower",
    sheets: [],
  });
}

function command(workbook, type, payload = {}) {
  return executeComputeCommand(workbook, { type, payload }, { actor: "planner@example.test" });
}

test("runtime formulas honor precedence without eval and reject unsafe or cyclic expressions", () => {
  assert.equal(evaluateRuntimeFormula("units * price + freight / 2", { units: 4, price: 12.5, freight: 6 }), 53);
  assert.equal(evaluateRuntimeFormula("-(a - 3) * 2", { a: 8 }), -10);
  assert.throws(() => evaluateRuntimeFormula("Math.max(a, 2)", { a: 1 }), /unsupported formula token|unexpected formula token/);
  assert.throws(() => evaluateRuntimeFormula("a / 0", { a: 1 }), /division by zero/);

  const workbook = workbookFixture();
  const cyclic = command(workbook, "schema.upsert", {
    id: "cycle",
    fields: [
      { id: "left", type: "formula", expression: "right + 1" },
      { id: "right", type: "formula", expression: "left + 1" },
    ],
  });
  assert.equal(cyclic.code, "validation");
  assert.match(cyclic.message, /formula cycle/);
});

test("runtime schemas enforce required, unique, reference, formula, and safe migration contracts", () => {
  const workbook = workbookFixture();
  assert.equal(command(workbook, "schema.upsert", {
    id: "suppliers",
    name: "Suppliers",
    fields: [{ id: "code", label: "Supplier code", type: "string", required: true, unique: true }],
  }).ok, true);
  const supplier = command(workbook, "schema.record.upsert", {
    schemaId: "suppliers",
    values: { code: "SUP-01" },
  });
  assert.equal(supplier.ok, true);

  assert.equal(command(workbook, "schema.upsert", {
    id: "parts",
    name: "Parts",
    fields: [
      { id: "sku", type: "string", required: true, unique: true },
      { id: "supplier", type: "reference", referenceSchemaId: "suppliers", required: true },
      { id: "units", type: "number", required: true },
      { id: "unit_cost", type: "number", required: true },
      { id: "landed_cost", type: "formula", expression: "units * unit_cost" },
    ],
  }).ok, true);

  const invalidReference = command(workbook, "schema.record.upsert", {
    schemaId: "parts",
    values: { sku: "P-01", supplier: "missing", units: 4, unit_cost: 12.5 },
  });
  assert.equal(invalidReference.code, "validation");
  assert.match(invalidReference.message, /unknown record/);

  const part = command(workbook, "schema.record.upsert", {
    schemaId: "parts",
    values: { sku: "P-01", supplier: supplier.item.id, units: 4, unit_cost: 12.5 },
  });
  assert.equal(part.item.values.landed_cost, 50);

  const duplicate = command(workbook, "schema.record.upsert", {
    schemaId: "parts",
    values: { sku: "P-01", supplier: supplier.item.id, units: 1, unit_cost: 2 },
  });
  assert.equal(duplicate.code, "validation");
  assert.match(duplicate.message, /unique/);

  const versionBefore = workbook.enterprise.schemas.find((schema) => schema.id === "parts").version;
  const rejectedMigration = command(workbook, "schema.upsert", {
    id: "parts",
    fields: [
      { id: "sku", type: "string", required: true, unique: true },
      { id: "category", type: "string", required: true },
    ],
  });
  assert.equal(rejectedMigration.code, "validation");
  assert.equal(workbook.enterprise.schemas.find((schema) => schema.id === "parts").version, versionBefore);
  assert.equal(workbook.enterprise.records.parts[0].values.landed_cost, 50);
});

test("general ledger rejects imbalance and preserves immutable balanced reversals", () => {
  const workbook = workbookFixture();
  for (const account of [
    { code: "1000", name: "Cash", accountType: "asset", currency: "CNY" },
    { code: "3000", name: "Opening equity", accountType: "equity", currency: "CNY" },
  ]) assert.equal(command(workbook, "ledger.account.upsert", account).ok, true);

  const unbalanced = command(workbook, "ledger.journal.post", {
    date: "2026-09-01",
    currency: "CNY",
    lines: [
      { accountCode: "1000", debit: 100 },
      { accountCode: "3000", credit: 99.99 },
    ],
  });
  assert.equal(unbalanced.code, "validation");
  assert.equal(workbook.enterprise.ledger.journals.length, 0);

  const posted = command(workbook, "ledger.journal.post", {
    date: "2026-09-01",
    reference: "OPEN-001",
    memo: "Opening balance",
    currency: "CNY",
    lines: [
      { accountCode: "1000", debit: 100.25 },
      { accountCode: "3000", credit: 100.25 },
    ],
  });
  assert.equal(posted.ok, true);
  assert.equal(posted.item.hash.length, 64);
  assert.deepEqual(trialBalance(workbook.enterprise), {
    rows: [
      { code: "1000", name: "Cash", type: "asset", debit: 100.25, credit: 0, balance: 100.25 },
      { code: "3000", name: "Opening equity", type: "equity", debit: 0, credit: 100.25, balance: -100.25 },
    ],
    debit: 100.25,
    credit: 100.25,
    balanced: true,
  });

  const reversed = command(workbook, "ledger.journal.reverse", { id: posted.item.id, date: "2026-09-02" });
  assert.equal(reversed.ok, true);
  assert.equal(reversed.item.reversalOf, posted.item.id);
  assert.equal(workbook.enterprise.ledger.journals.length, 2);
  assert.equal(trialBalance(workbook.enterprise).rows.every((row) => row.balance === 0), true);
  assert.equal(command(workbook, "ledger.journal.reverse", { id: posted.item.id }).code, "validation");
});

test("journal retries are idempotent and closed accounting periods reject back-posting", () => {
  const workbook = workbookFixture();
  command(workbook, "ledger.account.upsert", { code: "1000", accountType: "asset" });
  command(workbook, "ledger.account.upsert", { code: "4000", accountType: "revenue" });
  const payload = {
    date: "2026-09-15",
    reference: "INV-2026-009",
    lines: [{ accountCode: "1000", debit: 25 }, { accountCode: "4000", credit: 25 }],
  };
  const first = command(workbook, "ledger.journal.post", payload);
  const eventsAfterFirst = workbook.enterprise.computeEvents.length;
  const replay = command(workbook, "ledger.journal.post", structuredClone(payload));
  assert.equal(replay.ok, true);
  assert.equal(replay.replayed, true);
  assert.equal(replay.item.id, first.item.id);
  assert.equal(workbook.enterprise.ledger.journals.length, 1);
  assert.equal(workbook.enterprise.computeEvents.length, eventsAfterFirst);

  const conflict = command(workbook, "ledger.journal.post", {
    ...payload,
    lines: [{ accountCode: "1000", debit: 30 }, { accountCode: "4000", credit: 30 }],
  });
  assert.equal(conflict.code, "idempotency_conflict");
  assert.equal(workbook.enterprise.ledger.journals.length, 1);

  assert.equal(command(workbook, "ledger.period.close", { period: "2026-09" }).ok, true);
  const backPost = command(workbook, "ledger.journal.post", {
    date: "2026-09-30",
    reference: "INV-2026-010",
    lines: [{ accountCode: "1000", debit: 10 }, { accountCode: "4000", credit: 10 }],
  });
  assert.equal(backPost.code, "validation");
  assert.match(backPost.message, /period is closed/);
  assert.equal(command(workbook, "ledger.period.reopen", { period: "2026-09", confirmPeriod: "wrong" }).code, "validation");
  assert.equal(command(workbook, "ledger.period.reopen", { period: "2026-09", confirmPeriod: "2026-09" }).ok, true);
  assert.equal(command(workbook, "ledger.journal.post", {
    date: "2026-09-30",
    reference: "INV-2026-010",
    lines: [{ accountCode: "1000", debit: 10 }, { accountCode: "4000", credit: 10 }],
  }).ok, true);
  assert.equal(verifyComputeState(workbook.enterprise).valid, true);
});

test("BOM cycles fail atomically and multi-level MRP explodes net requirements with lead times", () => {
  const workbook = workbookFixture();
  const items = [
    { id: "FG-100", name: "Finished unit", itemType: "manufactured", onHand: 1, leadTimeDays: 2, lotSize: 1 },
    { id: "SUB-10", name: "Subassembly", itemType: "manufactured", leadTimeDays: 1, lotSize: 1 },
    { id: "RAW-1", name: "Raw material", itemType: "purchased", leadTimeDays: 3, lotSize: 1 },
  ];
  for (const item of items) assert.equal(command(workbook, "mrp.item.upsert", item).ok, true);
  assert.equal(command(workbook, "mrp.bom.upsert", { parentId: "FG-100", componentId: "SUB-10", quantity: 2 }).ok, true);
  assert.equal(command(workbook, "mrp.bom.upsert", { parentId: "SUB-10", componentId: "RAW-1", quantity: 3 }).ok, true);

  const cyclic = command(workbook, "mrp.bom.upsert", { parentId: "RAW-1", componentId: "FG-100", quantity: 1 });
  assert.equal(cyclic.code, "validation");
  assert.match(cyclic.message, /BOM cycle/);
  assert.equal(workbook.enterprise.mrp.bom.length, 2);

  assert.equal(command(workbook, "mrp.demand.upsert", {
    id: "SO-42",
    itemId: "FG-100",
    quantity: 5,
    dueDate: "2026-09-20",
  }).ok, true);
  const result = command(workbook, "mrp.run", { asOfDate: "2026-09-01" });
  assert.equal(result.ok, true);
  assert.equal(result.item.inputHash.length, 64);
  assert.equal(result.item.outputHash.length, 64);
  assert.deepEqual(result.item.rows.map((row) => ({
    itemId: row.itemId,
    gross: row.grossRequirement,
    order: row.plannedOrder,
    due: row.dueDate,
    release: row.releaseDate,
  })), [
    { itemId: "FG-100", gross: 5, order: 4, due: "2026-09-20", release: "2026-09-18" },
    { itemId: "SUB-10", gross: 8, order: 8, due: "2026-09-18", release: "2026-09-17" },
    { itemId: "RAW-1", gross: 24, order: 24, due: "2026-09-17", release: "2026-09-14" },
  ]);
  assert.equal(result.item.rows.some((row) => row.late), false);
});

test("dated receipts are applied only when available and remain pegged to chronological demand", () => {
  const workbook = workbookFixture();
  command(workbook, "mrp.item.upsert", { id: "RAW-1", itemType: "purchased", onHand: 0, lotSize: 10, leadTimeDays: 2 });
  command(workbook, "mrp.receipt.upsert", { id: "PO-1", itemId: "RAW-1", quantity: 6, dueDate: "2026-10-10", reference: "PO-1" });
  command(workbook, "mrp.demand.upsert", { id: "EARLY", itemId: "RAW-1", quantity: 5, dueDate: "2026-10-09" });
  command(workbook, "mrp.demand.upsert", { id: "ON-TIME", itemId: "RAW-1", quantity: 6, dueDate: "2026-10-10" });
  const plan = command(workbook, "mrp.run", { asOfDate: "2026-10-01" }).item.rows;
  assert.deepEqual(plan.map((row) => ({ source: row.source, receipt: row.scheduledReceiptsApplied, order: row.plannedOrder, projected: row.projectedAvailable })), [
    { source: "EARLY", receipt: 0, order: 10, projected: 5 },
    { source: "ON-TIME", receipt: 6, order: 0, projected: 5 },
  ]);
});

test("compute event evidence is chained and MRP is deterministic for a frozen state", () => {
  const workbook = workbookFixture();
  command(workbook, "mrp.item.upsert", { id: "P-1", itemType: "purchased", lotSize: 5, leadTimeDays: 2 });
  command(workbook, "mrp.demand.upsert", { id: "D-1", itemId: "P-1", quantity: 6, dueDate: "2026-10-10" });
  const firstRows = runMrp(workbook.enterprise.mrp, "2026-10-01");
  const secondRows = runMrp(structuredClone(workbook.enterprise.mrp), "2026-10-01");
  assert.deepEqual(firstRows, secondRows);

  const events = workbook.enterprise.computeEvents;
  assert.equal(events.length, 2);
  assert.equal(events[0].previousHash, "GENESIS");
  assert.equal(events[1].previousHash, events[0].hash);
  assert.equal(events.every((event) => event.hash.length === 64 && event.inputHash.length === 64 && event.outputHash.length === 64 && event.stateHash.length === 64), true);
  assert.equal(verifyComputeState(workbook.enterprise).valid, true);
});

test("compute integrity failures are observable and block every later mutation", () => {
  const eventTamper = workbookFixture();
  assert.equal(command(eventTamper, "mrp.item.upsert", { id: "P-1", itemType: "purchased" }).ok, true);
  eventTamper.enterprise.computeEvents[0].actor = "tampered";
  const eventIntegrity = command(eventTamper, "compute.verify");
  assert.equal(eventIntegrity.ok, true);
  assert.equal(eventIntegrity.item.valid, false);
  const eventCount = eventTamper.enterprise.computeEvents.length;
  const blockedItem = command(eventTamper, "mrp.item.upsert", { id: "P-2", itemType: "purchased" });
  assert.equal(blockedItem.code, "integrity");
  assert.equal(eventTamper.enterprise.mrp.items.some((item) => item.id === "P-2"), false);
  assert.equal(eventTamper.enterprise.computeEvents.length, eventCount);

  const journalTamper = workbookFixture();
  command(journalTamper, "ledger.account.upsert", { code: "A", accountType: "asset" });
  command(journalTamper, "ledger.account.upsert", { code: "E", accountType: "equity" });
  command(journalTamper, "ledger.journal.post", {
    date: "2026-09-01",
    lines: [{ accountCode: "A", debit: 10 }, { accountCode: "E", credit: 10 }],
  });
  journalTamper.enterprise.ledger.journals[0].lines[0].debitCents += 1;
  journalTamper.enterprise.ledger.journals[0].lines[1].creditCents += 1;
  const journalIntegrity = command(journalTamper, "compute.verify");
  assert.equal(journalIntegrity.item.valid, false);
  assert.equal(journalIntegrity.item.layer, "ledger");
  assert.equal(command(journalTamper, "ledger.account.upsert", { code: "R", accountType: "revenue" }).code, "integrity");

  const stateTamper = workbookFixture();
  command(stateTamper, "mrp.item.upsert", { id: "RAW-1", itemType: "purchased", onHand: 5 });
  stateTamper.enterprise.mrp.items[0].onHand = 5000;
  const stateIntegrity = command(stateTamper, "compute.verify");
  assert.equal(stateIntegrity.item.valid, false);
  assert.equal(stateIntegrity.item.layer, "business_state");
  assert.equal(stateIntegrity.item.reason, "state_hash_mismatch");
});

test("deterministic randomized ledger mutations preserve balance and reject partial writes", () => {
  const workbook = workbookFixture();
  command(workbook, "ledger.account.upsert", { code: "A", name: "Asset", accountType: "asset" });
  command(workbook, "ledger.account.upsert", { code: "E", name: "Equity", accountType: "equity" });
  let state = 0x5eed1234;
  function next() {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state;
  }
  for (let index = 0; index < 200; index += 1) {
    const amount = ((next() % 100_000) + 1) / 100;
    const before = workbook.enterprise.ledger.journals.length;
    if (index % 17 === 0) {
      const rejected = command(workbook, "ledger.journal.post", {
        date: "2026-09-01",
        lines: [
          { accountCode: "A", debit: amount },
          { accountCode: "E", credit: amount + 0.01 },
        ],
      });
      assert.equal(rejected.code, "validation");
      assert.equal(workbook.enterprise.ledger.journals.length, before);
      continue;
    }
    const posted = command(workbook, "ledger.journal.post", {
      date: "2026-09-01",
      lines: index % 2
        ? [{ accountCode: "A", debit: amount }, { accountCode: "E", credit: amount }]
        : [{ accountCode: "E", debit: amount }, { accountCode: "A", credit: amount }],
    });
    assert.equal(posted.ok, true);
  }
  const balance = trialBalance(workbook.enterprise);
  assert.equal(balance.balanced, true);
  assert.equal(balance.debit, balance.credit);
});

test("deterministic randomized acyclic BOMs produce finite reproducible plans", () => {
  const mrp = { items: [], bom: [], demands: [], runs: [] };
  for (let index = 0; index < 24; index += 1) {
    mrp.items.push({
      id: `I-${index}`,
      name: `Item ${index}`,
      type: index < 12 ? "manufactured" : "purchased",
      onHand: index % 4,
      scheduledReceipts: index % 3,
      safetyStock: index % 2,
      leadTimeDays: (index % 5) + 1,
      lotSize: (index % 4) + 1,
    });
  }
  for (let parent = 0; parent < 12; parent += 1) {
    for (const offset of [1, 3]) {
      const component = Math.min(23, parent + offset + 8);
      mrp.bom.push({
        id: `I-${parent}:I-${component}`,
        parentId: `I-${parent}`,
        componentId: `I-${component}`,
        quantity: (parent % 3) + 1,
        scrapRate: (parent % 4) / 100,
      });
    }
  }
  mrp.demands.push(
    { id: "D-0", itemId: "I-0", quantity: 7, dueDate: "2026-10-30" },
    { id: "D-1", itemId: "I-1", quantity: 11, dueDate: "2026-11-03" },
  );
  const first = runMrp(mrp, "2026-09-01");
  const second = runMrp(structuredClone(mrp), "2026-09-01");
  assert.deepEqual(first, second);
  assert.ok(first.length > 2 && first.length < 10_000);
  for (const row of first) {
    for (const field of ["grossRequirement", "availableBefore", "netRequirement", "plannedOrder", "projectedAvailable"]) {
      assert.equal(Number.isFinite(row[field]), true, `${row.itemId}.${field}`);
      assert.ok(row[field] >= 0, `${row.itemId}.${field}`);
    }
  }
});
