let context = null;
let activeView = "overview";
let selectedSchemaId = "";
let editingSchemaId = "";
let trialBalance = null;
let integrityResult = null;
let notice = null;
let busy = false;

function html(value) {
  return context.escapeHtml(value ?? "");
}

function enterprise() {
  return context.workbook.enterprise || {
    revision: 0,
    schemas: [],
    records: {},
    ledger: { accounts: [], journals: [] },
    mrp: { items: [], bom: [], demands: [], runs: [] },
    computeEvents: [],
  };
}

function option(value, label, selected = false) {
  return `<option value="${html(value)}" ${selected ? "selected" : ""}>${html(label)}</option>`;
}

function money(value) {
  return new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value || 0));
}

function shortHash(value) {
  const text = String(value || "");
  return text ? `${text.slice(0, 10)}…${text.slice(-6)}` : "—";
}

function navButton(view, label, detail) {
  return `<button type="button" class="compute-nav-button" data-compute-view="${view}" aria-current="${activeView === view ? "page" : "false"}">
    <strong>${html(label)}</strong><span>${html(detail)}</span>
  </button>`;
}

function emptyState(title, detail) {
  return `<div class="compute-empty"><strong>${html(title)}</strong><span>${html(detail)}</span></div>`;
}

function statusMarkup() {
  if (!notice) return "";
  return `<div class="compute-notice ${notice.kind}" role="${notice.kind === "error" ? "alert" : "status"}">${html(notice.message)}</div>`;
}

function metric(label, value, detail) {
  return `<article class="compute-metric"><span>${html(label)}</span><strong>${html(value)}</strong><small>${html(detail)}</small></article>`;
}

function overviewMarkup() {
  const data = enterprise();
  const latestRun = data.mrp.runs.at(-1);
  return `<section aria-labelledby="compute-overview-heading">
    <div class="compute-hero">
      <div>
        <span class="compute-eyebrow">Deterministic enterprise kernel</span>
        <h2 id="compute-overview-heading">Turn a workbook into an auditable operating system.</h2>
        <p>Define data at runtime, post balanced financial events, and explode multi-level material plans. Every accepted mutation is validated, versioned, and chained to evidence.</p>
      </div>
      <button type="button" class="primary compute-hero-action" id="load-factory-demo" ${busy ? "disabled" : ""}>${busy ? "Building demo…" : "Build guided factory demo"}</button>
    </div>
    <div class="compute-metrics">
      ${metric("Runtime schemas", data.schemas.length, "typed, referenced, formula-backed")}
      ${metric("Posted journals", data.ledger.journals.length, "integer-cent double entry")}
      ${metric("BOM relationships", data.mrp.bom.length, "cycle checked before commit")}
      ${metric("Evidence events", data.computeEvents.length, `revision ${data.revision}`)}
    </div>
    <div class="compute-grid compute-grid-2">
      <article class="compute-panel">
        <span class="compute-kicker">One invariant chain</span>
        <h3>Requirements → validation → transaction → evidence</h3>
        <ol class="compute-flow">
          <li><b>1</b><span><strong>Runtime contract</strong>Typed fields, unique keys, references, and safe formulas.</span></li>
          <li><b>2</b><span><strong>Fail-closed execution</strong>Invalid dates, imbalance, stale revisions, and BOM cycles never commit.</span></li>
          <li><b>3</b><span><strong>Operational result</strong>Trial balances and lead-time-aware plans are computed from persisted facts.</span></li>
          <li><b>4</b><span><strong>Production evidence</strong>Input/output hashes form a tamper-evident event chain.</span></li>
        </ol>
      </article>
      <article class="compute-panel compute-control-panel">
        <span class="compute-kicker">Current control state</span>
        <h3>${latestRun ? "Planning run available" : "Ready for a controlled run"}</h3>
        <dl class="compute-definition-list">
          <div><dt>Workbook revision</dt><dd>${data.revision}</dd></div>
          <div><dt>Latest MRP output</dt><dd>${latestRun ? `${latestRun.rows.length} requirements` : "Not run"}</dd></div>
          <div><dt>Latest output hash</dt><dd title="${html(latestRun?.outputHash || "")}">${html(shortHash(latestRun?.outputHash))}</dd></div>
          <div><dt>Last mutation</dt><dd>${html(data.computeEvents.at(-1)?.action || "None")}</dd></div>
        </dl>
        <div class="compute-inline-actions">
          <button type="button" class="secondary" data-compute-view="schema">Open data contracts</button>
          <button type="button" class="secondary" data-compute-view="mrp">Open planning</button>
        </div>
      </article>
    </div>
  </section>`;
}

function schemaDefinition(schema) {
  return JSON.stringify(schema?.fields || [
    { id: "sku", label: "SKU", type: "string", required: true, unique: true },
    { id: "quantity", label: "Quantity", type: "number", required: true },
    { id: "unit_cost", label: "Unit cost", type: "number", required: true },
    { id: "extended_cost", label: "Extended cost", type: "formula", expression: "quantity * unit_cost" },
  ], null, 2);
}

function recordInput(field, data) {
  const id = `record-${field.id}`;
  if (field.type === "formula") {
    return `<label class="compute-field"><span>${html(field.label)}</span><input value="Computed: ${html(field.expression)}" disabled /></label>`;
  }
  if (field.type === "enum") {
    return `<label class="compute-field" for="${id}"><span>${html(field.label)}${field.required ? " *" : ""}</span><select id="${id}" name="${html(field.id)}"><option value="">Select…</option>${field.options.map((value) => option(value, value)).join("")}</select></label>`;
  }
  if (field.type === "reference") {
    const target = data.schemas.find((schema) => schema.id === field.referenceSchemaId);
    const records = data.records[field.referenceSchemaId] || [];
    return `<label class="compute-field" for="${id}"><span>${html(field.label)}${field.required ? " *" : ""}</span><select id="${id}" name="${html(field.id)}"><option value="">Select ${html(target?.name || field.referenceSchemaId)}…</option>${records.map((record) => option(record.id, Object.values(record.values || {})[0] || record.id)).join("")}</select></label>`;
  }
  if (field.type === "boolean") {
    return `<label class="compute-field" for="${id}"><span>${html(field.label)}</span><select id="${id}" name="${html(field.id)}">${option("true", "True")}${option("false", "False")}</select></label>`;
  }
  const inputType = field.type === "number" ? "number" : field.type === "date" ? "date" : "text";
  return `<label class="compute-field" for="${id}"><span>${html(field.label)}${field.required ? " *" : ""}</span><input id="${id}" name="${html(field.id)}" type="${inputType}" ${inputType === "number" ? "step=\"any\"" : ""} ${field.required ? "required" : ""} /></label>`;
}

function recordsTable(schema, records) {
  if (!records.length) return emptyState("No records yet", "The generated form enforces this schema before any record is committed.");
  return `<div class="compute-table-wrap"><table class="compute-table"><thead><tr><th>Record</th>${schema.fields.map((field) => `<th>${html(field.label)}</th>`).join("")}</tr></thead><tbody>${records.map((record) => `<tr><td><code>${html(record.id.slice(0, 8))}</code></td>${schema.fields.map((field) => `<td>${html(record.values?.[field.id])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

function schemaMarkup() {
  const data = enterprise();
  const selected = data.schemas.find((schema) => schema.id === selectedSchemaId) || data.schemas[0] || null;
  if (selected && !selectedSchemaId) selectedSchemaId = selected.id;
  const editing = data.schemas.find((schema) => schema.id === editingSchemaId) || null;
  const records = selected ? data.records[selected.id] || [] : [];
  return `<section aria-labelledby="schema-heading">
    <div class="compute-section-heading"><div><span class="compute-eyebrow">Runtime data contracts</span><h2 id="schema-heading">Schema studio</h2><p>Create typed business objects without redeploying code. References and formulas are validated server-side.</p></div><span class="compute-chip">${data.schemas.length} schemas</span></div>
    <div class="compute-grid compute-grid-2">
      <form class="compute-panel compute-form" id="schema-form">
        <div class="compute-panel-heading"><div><span class="compute-kicker">Contract editor</span><h3>${editing ? `Edit ${html(editing.name)}` : "Create schema"}</h3></div>${editing ? '<button type="button" class="secondary" id="cancel-schema-edit">New schema</button>' : ""}</div>
        <div class="compute-form-row">
          <label class="compute-field" for="schema-id"><span>Schema ID</span><input id="schema-id" name="id" pattern="[a-z][a-z0-9-]*" value="${html(editing?.id || "inventory-items")}" ${editing ? "readonly" : ""} required /></label>
          <label class="compute-field" for="schema-name"><span>Display name</span><input id="schema-name" name="name" value="${html(editing?.name || "Inventory items")}" required /></label>
        </div>
        <label class="compute-field" for="schema-fields"><span>Field definitions (JSON)</span><textarea id="schema-fields" name="fields" rows="13" spellcheck="false" required>${html(schemaDefinition(editing))}</textarea></label>
        <p class="compute-help">Types: string, number, boolean, date, enum, reference, formula. Formula grammar only permits field names and arithmetic.</p>
        <button class="primary" type="submit" ${busy ? "disabled" : ""}>Validate and save schema</button>
      </form>
      <article class="compute-panel">
        <div class="compute-panel-heading"><div><span class="compute-kicker">Deployed contracts</span><h3>Schema registry</h3></div></div>
        ${data.schemas.length ? `<div class="schema-list">${data.schemas.map((schema) => `<article class="schema-list-item ${selected?.id === schema.id ? "selected" : ""}"><button type="button" data-open-schema="${html(schema.id)}"><strong>${html(schema.name)}</strong><span>${schema.fields.length} fields · v${schema.version}</span></button><button type="button" class="secondary compact" data-edit-schema="${html(schema.id)}">Edit</button></article>`).join("")}</div>` : emptyState("No runtime schemas", "Save the sample inventory contract to create the first one.")}
      </article>
    </div>
    ${selected ? `<article class="compute-panel compute-records-panel">
      <div class="compute-panel-heading"><div><span class="compute-kicker">Generated interface</span><h3>${html(selected.name)} records</h3></div><span class="compute-chip">${records.length} records</span></div>
      <form id="record-form" class="compute-generated-form">${selected.fields.map((field) => recordInput(field, data)).join("")}<button class="primary" type="submit" ${busy ? "disabled" : ""}>Create validated record</button></form>
      ${recordsTable(selected, records)}
    </article>` : ""}
  </section>`;
}

function accountOptions(accounts) {
  return accounts.map((account) => option(account.code, `${account.code} · ${account.name}`)).join("");
}

function balanceTable(balance) {
  if (!balance) return emptyState("Trial balance not calculated", "Run it after posting a journal to independently verify total debits and credits.");
  return `<div class="compute-table-wrap"><table class="compute-table"><thead><tr><th>Account</th><th>Type</th><th class="number">Debit</th><th class="number">Credit</th><th class="number">Balance</th></tr></thead><tbody>${balance.rows.map((row) => `<tr><td><strong>${html(row.code)}</strong> ${html(row.name)}</td><td>${html(row.type)}</td><td class="number">${money(row.debit)}</td><td class="number">${money(row.credit)}</td><td class="number">${money(row.balance)}</td></tr>`).join("")}</tbody><tfoot><tr><th colspan="2">Control total</th><th class="number">${money(balance.debit)}</th><th class="number">${money(balance.credit)}</th><th><span class="compute-chip ${balance.balanced ? "success" : "danger"}">${balance.balanced ? "Balanced" : "Out of balance"}</span></th></tr></tfoot></table></div>`;
}

function ledgerMarkup() {
  const data = enterprise();
  const { accounts, journals, closedPeriods = [] } = data.ledger;
  const today = new Date().toISOString().slice(0, 10);
  const currentPeriod = today.slice(0, 7);
  return `<section aria-labelledby="ledger-heading">
    <div class="compute-section-heading"><div><span class="compute-eyebrow">Financial control plane</span><h2 id="ledger-heading">General ledger</h2><p>Post immutable double-entry journals in integer cents. Invalid or cross-currency entries fail before state changes.</p></div><span class="compute-chip success">${journals.length} posted</span></div>
    <div class="compute-grid compute-grid-2">
      <form class="compute-panel compute-form" id="account-form">
        <span class="compute-kicker">Chart of accounts</span><h3>Add or update account</h3>
        <div class="compute-form-row">
          <label class="compute-field" for="account-code"><span>Account code</span><input id="account-code" name="code" placeholder="1000" required /></label>
          <label class="compute-field" for="account-name"><span>Account name</span><input id="account-name" name="name" placeholder="Cash" required /></label>
        </div>
        <div class="compute-form-row">
          <label class="compute-field" for="account-type"><span>Account type</span><select id="account-type" name="accountType">${["asset", "liability", "equity", "revenue", "expense"].map((value) => option(value, value[0].toUpperCase() + value.slice(1))).join("")}</select></label>
          <label class="compute-field" for="account-currency"><span>Currency</span><input id="account-currency" name="currency" value="CNY" maxlength="8" required /></label>
        </div>
        <button class="primary" type="submit" ${busy ? "disabled" : ""}>Save account</button>
        ${accounts.length ? `<div class="compute-table-wrap compact-table"><table class="compute-table"><thead><tr><th>Code</th><th>Name</th><th>Type</th><th>Currency</th></tr></thead><tbody>${accounts.map((account) => `<tr><td><code>${html(account.code)}</code></td><td>${html(account.name)}</td><td>${html(account.type)}</td><td>${html(account.currency)}</td></tr>`).join("")}</tbody></table></div>` : emptyState("No accounts", "Create at least two accounts before posting a journal.")}
      </form>
      <form class="compute-panel compute-form" id="journal-form">
        <span class="compute-kicker">Immutable transaction</span><h3>Post journal entry</h3>
        <div class="compute-form-row">
          <label class="compute-field" for="journal-date"><span>Posting date</span><input id="journal-date" name="date" type="date" value="${today}" required /></label>
          <label class="compute-field" for="journal-reference"><span>Reference</span><input id="journal-reference" name="reference" placeholder="INV-2026-001" /></label>
        </div>
        <label class="compute-field" for="journal-memo"><span>Memo</span><input id="journal-memo" name="memo" placeholder="Opening inventory" /></label>
        <div class="journal-lines">
          <label class="compute-field" for="debit-account"><span>Debit account</span><select id="debit-account" name="debitAccount" required><option value="">Select…</option>${accountOptions(accounts)}</select></label>
          <label class="compute-field" for="debit-amount"><span>Debit amount</span><input id="debit-amount" name="debit" type="number" min="0.01" step="0.01" required /></label>
          <label class="compute-field" for="credit-account"><span>Credit account</span><select id="credit-account" name="creditAccount" required><option value="">Select…</option>${accountOptions(accounts)}</select></label>
          <label class="compute-field" for="credit-amount"><span>Credit amount</span><input id="credit-amount" name="credit" type="number" min="0.01" step="0.01" required /></label>
        </div>
        <button class="primary" type="submit" ${busy || accounts.length < 2 ? "disabled" : ""}>Validate and post</button>
      </form>
    </div>
    <article class="compute-panel">
      <div class="compute-panel-heading"><div><span class="compute-kicker">Independent control</span><h3>Trial balance</h3></div><button type="button" class="secondary" id="run-trial-balance">Recalculate</button></div>
      ${balanceTable(trialBalance)}
    </article>
    <article class="compute-panel">
      <div class="compute-panel-heading"><div><span class="compute-kicker">Period governance</span><h3>Accounting close</h3><p>Closed months reject new journals while later-period reversing entries remain available.</p></div><form id="period-close-form" class="compute-run-form"><label for="close-period">Period</label><input id="close-period" name="period" type="month" value="${currentPeriod}" required /><button class="secondary" type="submit">Close period</button></form></div>
      ${closedPeriods.length ? `<div class="compute-inline-actions">${closedPeriods.map((period) => `<span class="compute-chip">${html(period)} closed <button type="button" class="compute-chip-button" data-reopen-period="${html(period)}">Reopen</button></span>`).join("")}</div>` : emptyState("No closed periods", "Close a month to prevent accidental back-posting after reporting.")}
    </article>
    <article class="compute-panel">
      <div class="compute-panel-heading"><div><span class="compute-kicker">Append-only journal</span><h3>Posted entries</h3></div></div>
      ${journals.length ? `<div class="compute-table-wrap"><table class="compute-table"><thead><tr><th>Sequence</th><th>Date</th><th>Reference</th><th>Memo</th><th class="number">Debit</th><th class="number">Credit</th><th>Evidence</th><th></th></tr></thead><tbody>${journals.slice().reverse().map((journal) => `<tr><td>#${journal.sequence}</td><td>${html(journal.date)}</td><td>${html(journal.reference)}</td><td>${html(journal.memo || (journal.reversalOf ? "Reversal" : "—"))}</td><td class="number">${money(journal.debit)}</td><td class="number">${money(journal.credit)}</td><td><code title="${html(journal.hash)}">${html(shortHash(journal.hash))}</code></td><td>${journal.reversalOf || journals.some((entry) => entry.reversalOf === journal.id) ? '<span class="compute-chip">Closed</span>' : `<button type="button" class="secondary compact" data-reverse-journal="${html(journal.id)}">Reverse</button>`}</td></tr>`).join("")}</tbody></table></div>` : emptyState("No journal entries", "An unbalanced entry will be rejected without leaving a partial journal.")}
    </article>
  </section>`;
}

function latestPlanMarkup(run) {
  if (!run) return emptyState("No planning run", "Load the guided demo or define items, BOM lines, and demand, then run MRP.");
  return `<div class="compute-run-summary"><span>As of <strong>${html(run.asOfDate)}</strong></span><span>Input <code title="${html(run.inputHash)}">${html(shortHash(run.inputHash))}</code></span><span>Output <code title="${html(run.outputHash)}">${html(shortHash(run.outputHash))}</code></span></div><div class="compute-table-wrap"><table class="compute-table"><thead><tr><th>Level</th><th>Item</th><th>Due</th><th>Release</th><th class="number">Gross</th><th class="number">Receipts</th><th class="number">Available</th><th class="number">Net</th><th class="number">Planned order</th><th class="number">Projected</th><th>Status</th></tr></thead><tbody>${run.rows.map((row) => `<tr><td>L${row.level}</td><td><strong>${html(row.itemId)}</strong><br><small>${html(row.itemName)}</small></td><td>${html(row.dueDate)}</td><td>${html(row.releaseDate)}</td><td class="number">${html(row.grossRequirement)}</td><td class="number">${html(row.scheduledReceiptsApplied || 0)}</td><td class="number">${html(row.availableBefore)}</td><td class="number">${html(row.netRequirement)}</td><td class="number"><strong>${html(row.plannedOrder)}</strong></td><td class="number">${html(row.projectedAvailable)}</td><td><span class="compute-chip ${row.late ? "danger" : "success"}">${row.late ? "Late" : "On time"}</span></td></tr>`).join("")}</tbody></table></div>`;
}

function mrpMarkup() {
  const data = enterprise();
  const { items, bom, demands, receipts = [], runs } = data.mrp;
  const itemChoices = items.map((item) => option(item.id, `${item.id} · ${item.name}`)).join("");
  const manufacturedChoices = items.filter((item) => item.type === "manufactured").map((item) => option(item.id, `${item.id} · ${item.name}`)).join("");
  const due = new Date(Date.now() + 21 * 86_400_000).toISOString().slice(0, 10);
  const latest = runs.at(-1);
  return `<section aria-labelledby="mrp-heading">
    <div class="compute-section-heading"><div><span class="compute-eyebrow">Factory planning engine</span><h2 id="mrp-heading">BOM & material requirements planning</h2><p>Net inventory, lot sizing, scrap, safety stock, and lead times are exploded through an acyclic multi-level product graph.</p></div><button type="button" class="primary" id="load-factory-demo" ${busy ? "disabled" : ""}>${busy ? "Building demo…" : "Load guided demo"}</button></div>
    <div class="compute-grid compute-grid-2">
      <form class="compute-panel compute-form" id="mrp-item-form">
        <span class="compute-kicker">Master data</span><h3>Item</h3>
        <label class="compute-field" for="item-id"><span>Item ID</span><input id="item-id" name="id" placeholder="FG-100" required /></label>
        <label class="compute-field" for="item-name"><span>Name</span><input id="item-name" name="name" placeholder="Finished assembly" required /></label>
        <label class="compute-field" for="item-type"><span>Supply type</span><select id="item-type" name="itemType">${option("purchased", "Purchased")}${option("manufactured", "Manufactured")}</select></label>
        <div class="compute-form-row"><label class="compute-field" for="item-on-hand"><span>On hand</span><input id="item-on-hand" name="onHand" type="number" min="0" step="any" value="0" /></label><label class="compute-field" for="item-safety"><span>Safety stock</span><input id="item-safety" name="safetyStock" type="number" min="0" step="any" value="0" /></label></div>
        <div class="compute-form-row"><label class="compute-field" for="item-lead"><span>Lead time days</span><input id="item-lead" name="leadTimeDays" type="number" min="0" step="1" value="1" /></label><label class="compute-field" for="item-lot"><span>Lot size</span><input id="item-lot" name="lotSize" type="number" min="0.000001" step="any" value="1" /></label></div>
        <button class="primary" type="submit">Save item</button>
      </form>
      <form class="compute-panel compute-form" id="bom-form">
        <span class="compute-kicker">Product graph</span><h3>BOM relationship</h3>
        <label class="compute-field" for="bom-parent"><span>Manufactured parent</span><select id="bom-parent" name="parentId" required><option value="">Select…</option>${manufacturedChoices}</select></label>
        <label class="compute-field" for="bom-component"><span>Component</span><select id="bom-component" name="componentId" required><option value="">Select…</option>${itemChoices}</select></label>
        <div class="compute-form-row"><label class="compute-field" for="bom-quantity"><span>Quantity per</span><input id="bom-quantity" name="quantity" type="number" min="0.000001" step="any" value="1" required /></label><label class="compute-field" for="bom-scrap"><span>Scrap rate</span><input id="bom-scrap" name="scrapRate" type="number" min="0" max="1" step="0.01" value="0" /></label></div>
        <p class="compute-help">The full graph is checked for cycles before this edge is committed.</p>
        <button class="primary" type="submit" ${items.length < 2 ? "disabled" : ""}>Validate and save BOM</button>
      </form>
      <form class="compute-panel compute-form" id="demand-form">
        <span class="compute-kicker">Independent demand</span><h3>Demand signal</h3>
        <label class="compute-field" for="demand-reference"><span>Reference</span><input id="demand-reference" name="reference" placeholder="SO-2026-042" /></label>
        <label class="compute-field" for="demand-item"><span>Demand item</span><select id="demand-item" name="itemId" required><option value="">Select…</option>${itemChoices}</select></label>
        <div class="compute-form-row"><label class="compute-field" for="demand-quantity"><span>Quantity</span><input id="demand-quantity" name="quantity" type="number" min="0.000001" step="any" value="10" required /></label><label class="compute-field" for="demand-date"><span>Due date</span><input id="demand-date" name="dueDate" type="date" value="${due}" required /></label></div>
        <button class="primary" type="submit" ${items.length < 1 ? "disabled" : ""}>Save demand</button>
      </form>
      <form class="compute-panel compute-form" id="receipt-form">
        <span class="compute-kicker">Time-phased supply</span><h3>Scheduled receipt</h3>
        <label class="compute-field" for="receipt-reference"><span>Reference</span><input id="receipt-reference" name="reference" placeholder="PO-2026-042" /></label>
        <label class="compute-field" for="receipt-item"><span>Item</span><select id="receipt-item" name="itemId" required><option value="">Select…</option>${itemChoices}</select></label>
        <div class="compute-form-row"><label class="compute-field" for="receipt-quantity"><span>Quantity</span><input id="receipt-quantity" name="quantity" type="number" min="0.000001" step="any" value="10" required /></label><label class="compute-field" for="receipt-date"><span>Available date</span><input id="receipt-date" name="dueDate" type="date" value="${due}" required /></label></div>
        <button class="primary" type="submit" ${items.length < 1 ? "disabled" : ""}>Save scheduled receipt</button>
      </form>
    </div>
    <div class="compute-grid compute-grid-2">
      <article class="compute-panel"><div class="compute-panel-heading"><div><span class="compute-kicker">Item master</span><h3>${items.length} items</h3></div></div>${items.length ? `<div class="compute-table-wrap"><table class="compute-table"><thead><tr><th>Item</th><th>Type</th><th class="number">On hand</th><th class="number">Safety</th><th class="number">Lead</th><th class="number">Lot</th></tr></thead><tbody>${items.map((item) => `<tr><td><strong>${html(item.id)}</strong><br><small>${html(item.name)}</small></td><td>${html(item.type)}</td><td class="number">${html(item.onHand)}</td><td class="number">${html(item.safetyStock)}</td><td class="number">${html(item.leadTimeDays)}d</td><td class="number">${html(item.lotSize)}</td></tr>`).join("")}</tbody></table></div>` : emptyState("No items", "Create an item or load the guided factory demo.")}</article>
      <article class="compute-panel"><div class="compute-panel-heading"><div><span class="compute-kicker">Bill of materials</span><h3>${bom.length} relationships</h3></div></div>${bom.length ? `<div class="compute-table-wrap"><table class="compute-table"><thead><tr><th>Parent</th><th>Component</th><th class="number">Quantity</th><th class="number">Scrap</th></tr></thead><tbody>${bom.map((line) => `<tr><td><strong>${html(line.parentId)}</strong></td><td>${html(line.componentId)}</td><td class="number">${html(line.quantity)}</td><td class="number">${html(Math.round(line.scrapRate * 10000) / 100)}%</td></tr>`).join("")}</tbody></table></div>` : emptyState("No BOM relationships", "Parent and component master data must exist first.")}</article>
    </div>
    <article class="compute-panel compute-plan-panel">
      <div class="compute-panel-heading"><div><span class="compute-kicker">Deterministic planning run</span><h3>Material plan</h3><p>${demands.length} demand signals · ${receipts.length} dated receipts · ${runs.length} immutable run snapshots</p></div><form id="mrp-run-form" class="compute-run-form"><label for="mrp-as-of">As-of date</label><input id="mrp-as-of" name="asOfDate" type="date" value="${new Date().toISOString().slice(0, 10)}" required /><button class="primary" type="submit" ${demands.length ? "" : "disabled"}>Run MRP</button></form></div>
      ${latestPlanMarkup(latest)}
    </article>
  </section>`;
}

function auditMarkup() {
  const data = enterprise();
  const events = data.computeEvents.slice().reverse();
  const integrityChip = integrityResult
    ? `<span class="compute-chip ${integrityResult.valid ? "success" : "danger"}">${integrityResult.valid ? "Verified" : "Integrity failure"}</span>`
    : `<span class="compute-chip">Not checked this session</span>`;
  return `<section aria-labelledby="compute-audit-heading">
    <div class="compute-section-heading"><div><span class="compute-eyebrow">Production trace</span><h2 id="compute-audit-heading">Compute evidence</h2><p>Each accepted mutation binds canonical input, output, and the complete business-state root to the previous event hash.</p></div><div class="compute-inline-actions">${integrityChip}<span class="compute-chip success">Chain head ${html(shortHash(events[0]?.hash))}</span><button type="button" class="secondary compact" id="verify-compute-integrity" ${busy ? "disabled" : ""}>Verify now</button></div></div>
    <article class="compute-panel">
      ${events.length ? `<div class="compute-table-wrap"><table class="compute-table"><thead><tr><th>Seq</th><th>Timestamp</th><th>Actor</th><th>Action</th><th>Input</th><th>Output</th><th>State root</th><th>Previous</th><th>Event</th></tr></thead><tbody>${events.map((event) => `<tr><td>#${event.sequence}</td><td>${html(new Date(event.timestamp).toLocaleString())}</td><td>${html(event.actor)}</td><td><code>${html(event.action)}</code></td><td><code title="${html(event.inputHash)}">${html(shortHash(event.inputHash))}</code></td><td><code title="${html(event.outputHash)}">${html(shortHash(event.outputHash))}</code></td><td><code title="${html(event.stateHash)}">${html(shortHash(event.stateHash))}</code></td><td><code title="${html(event.previousHash)}">${html(shortHash(event.previousHash))}</code></td><td><code title="${html(event.hash)}">${html(shortHash(event.hash))}</code></td></tr>`).join("")}</tbody></table></div>` : emptyState("No evidence events", "Validated mutations will appear here; rejected commands intentionally leave no event.")}
    </article>
  </section>`;
}

function contentMarkup() {
  if (activeView === "schema") return schemaMarkup();
  if (activeView === "ledger") return ledgerMarkup();
  if (activeView === "mrp") return mrpMarkup();
  if (activeView === "audit") return auditMarkup();
  return overviewMarkup();
}

function draw() {
  const data = enterprise();
  context.app.innerHTML = `<header class="topbar compute-topbar">
    <a href="/" class="secondary">Workbooks</a>
    <div><span class="compute-product">Langqi Compute</span><h1>${html(context.workbook.name)}</h1></div>
    <span class="compute-chip">v${data.version} · r${data.revision}</span>
    <span class="spacer"></span>
    <span class="status">${html(context.updatedText(context.workbook.updatedAt))}</span>
    <a class="secondary" href="/workbooks/${encodeURIComponent(context.workbook.id)}">Spreadsheet grid</a>
  </header>
  <div class="compute-shell">
    <aside class="compute-sidebar" aria-label="Enterprise compute navigation">
      <div class="compute-sidebar-brand"><span>LF</span><div><strong>Control tower</strong><small>fail-closed kernel</small></div></div>
      <nav>
        ${navButton("overview", "Overview", "control state")}
        ${navButton("schema", "Runtime schema", "typed contracts")}
        ${navButton("ledger", "General ledger", "double entry")}
        ${navButton("mrp", "BOM & MRP", "factory planning")}
        ${navButton("audit", "Evidence", "hash chain")}
      </nav>
      <div class="compute-sidebar-foot"><span class="compute-health-dot"></span><div><strong>Kernel ready</strong><small>${data.computeEvents.length} accepted mutations</small></div></div>
    </aside>
    <main class="compute-main">${statusMarkup()}${contentMarkup()}</main>
  </div>`;
  wire();
}

async function postCommand(type, payload = {}) {
  const response = await context.request(`/api/workbooks/${encodeURIComponent(context.workbook.id)}/compute`, {
    method: "POST",
    headers: { "x-langqi-user": "factory-planner" },
    body: JSON.stringify({ type, payload, expectedRevision: enterprise().revision }),
  });
  context.workbook.enterprise = response.enterprise;
  context.workbook.updatedAt = response.updatedAt;
  integrityResult = response.integrity || integrityResult;
  return response;
}

async function act(type, payload, successMessage, after) {
  if (busy) return;
  busy = true;
  notice = null;
  draw();
  try {
    const response = await postCommand(type, payload);
    if (after) after(response);
    notice = { kind: "success", message: successMessage };
  } catch (error) {
    notice = { kind: "error", message: error.message };
  } finally {
    busy = false;
    draw();
  }
}

async function loadFactoryDemo() {
  if (busy) return;
  busy = true;
  notice = null;
  draw();
  const dueDate = new Date(Date.now() + 21 * 86_400_000).toISOString().slice(0, 10);
  const receiptDate = new Date(Date.now() + 8 * 86_400_000).toISOString().slice(0, 10);
  const operations = [
    ["mrp.item.upsert", { id: "FG-100", name: "Crystal controller", itemType: "manufactured", onHand: 2, safetyStock: 1, leadTimeDays: 2, lotSize: 5 }],
    ["mrp.item.upsert", { id: "SUB-10", name: "Control board", itemType: "manufactured", onHand: 0, safetyStock: 0, leadTimeDays: 2, lotSize: 5 }],
    ["mrp.item.upsert", { id: "RAW-1", name: "Processor", itemType: "purchased", onHand: 8, safetyStock: 4, leadTimeDays: 5, lotSize: 20 }],
    ["mrp.item.upsert", { id: "RAW-2", name: "Crystal housing", itemType: "purchased", onHand: 12, safetyStock: 2, leadTimeDays: 3, lotSize: 10 }],
    ["mrp.bom.upsert", { parentId: "FG-100", componentId: "SUB-10", quantity: 1 }],
    ["mrp.bom.upsert", { parentId: "FG-100", componentId: "RAW-2", quantity: 2, scrapRate: 0.02 }],
    ["mrp.bom.upsert", { parentId: "SUB-10", componentId: "RAW-1", quantity: 2, scrapRate: 0.05 }],
    ["mrp.receipt.upsert", { id: "DEMO-PO-100", reference: "PO-2026-100", itemId: "RAW-1", quantity: 20, dueDate: receiptDate }],
    ["mrp.demand.upsert", { id: "DEMO-SO-100", reference: "SO-2026-100", itemId: "FG-100", quantity: 17, dueDate }],
    ["mrp.run", { asOfDate: new Date().toISOString().slice(0, 10) }],
  ];
  try {
    for (const [type, payload] of operations) await postCommand(type, payload);
    activeView = "mrp";
    notice = { kind: "success", message: "Guided factory created: 4 items, dated supply, a 2-level BOM, demand, and a hash-bound MRP run." };
  } catch (error) {
    notice = { kind: "error", message: `Guided demo stopped safely: ${error.message}` };
  } finally {
    busy = false;
    draw();
  }
}

function formValues(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function wire() {
  for (const button of document.querySelectorAll("[data-compute-view]")) button.addEventListener("click", () => {
    activeView = button.dataset.computeView;
    notice = null;
    draw();
  });
  document.querySelector("#load-factory-demo")?.addEventListener("click", () => void loadFactoryDemo());
  document.querySelector("#verify-compute-integrity")?.addEventListener("click", () => {
    void act("compute.verify", {}, "Evidence chain and ledger integrity verified.", (response) => { integrityResult = response.item; });
  });

  document.querySelector("#schema-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const values = formValues(event.currentTarget);
    try {
      values.fields = JSON.parse(values.fields);
    } catch {
      notice = { kind: "error", message: "Field definitions must be valid JSON." };
      draw();
      return;
    }
    void act("schema.upsert", values, `Schema ${values.id} validated and deployed.`, () => {
      selectedSchemaId = values.id;
      editingSchemaId = "";
    });
  });
  document.querySelector("#cancel-schema-edit")?.addEventListener("click", () => {
    editingSchemaId = "";
    draw();
  });
  for (const button of document.querySelectorAll("[data-open-schema]")) button.addEventListener("click", () => {
    selectedSchemaId = button.dataset.openSchema;
    draw();
  });
  for (const button of document.querySelectorAll("[data-edit-schema]")) button.addEventListener("click", () => {
    editingSchemaId = button.dataset.editSchema;
    selectedSchemaId = editingSchemaId;
    draw();
  });
  document.querySelector("#record-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    void act("schema.record.upsert", { schemaId: selectedSchemaId, values: formValues(event.currentTarget) }, "Record validated and committed.");
  });

  document.querySelector("#account-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const values = formValues(event.currentTarget);
    void act("ledger.account.upsert", values, `Account ${values.code} saved.`, () => { trialBalance = null; });
  });
  document.querySelector("#journal-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const values = formValues(event.currentTarget);
    const currency = enterprise().ledger.accounts.find((account) => account.code === values.debitAccount)?.currency || "CNY";
    void act("ledger.journal.post", {
      date: values.date,
      reference: values.reference,
      memo: values.memo,
      currency,
      lines: [
        { accountCode: values.debitAccount, debit: values.debit, credit: 0 },
        { accountCode: values.creditAccount, debit: 0, credit: values.credit },
      ],
    }, "Balanced journal posted with immutable evidence.", () => { trialBalance = null; });
  });
  document.querySelector("#run-trial-balance")?.addEventListener("click", () => {
    void act("ledger.trial_balance", {}, "Trial balance recalculated.", (response) => { trialBalance = response.item; });
  });
  document.querySelector("#period-close-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const values = formValues(event.currentTarget);
    void act("ledger.period.close", values, `Accounting period ${values.period} closed.`);
  });
  for (const button of document.querySelectorAll("[data-reopen-period]")) button.addEventListener("click", () => {
    const period = button.dataset.reopenPeriod;
    void act("ledger.period.reopen", { period, confirmPeriod: period }, `Accounting period ${period} reopened.`);
  });
  for (const button of document.querySelectorAll("[data-reverse-journal]")) button.addEventListener("click", () => {
    void act("ledger.journal.reverse", { id: button.dataset.reverseJournal }, "Reversing journal posted; original evidence remains intact.", () => { trialBalance = null; });
  });

  document.querySelector("#mrp-item-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const values = formValues(event.currentTarget);
    void act("mrp.item.upsert", values, `Item ${values.id} saved.`);
  });
  document.querySelector("#bom-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const values = formValues(event.currentTarget);
    void act("mrp.bom.upsert", values, "BOM graph validated and relationship saved.");
  });
  document.querySelector("#demand-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const values = formValues(event.currentTarget);
    void act("mrp.demand.upsert", values, "Demand signal saved.");
  });
  document.querySelector("#receipt-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    void act("mrp.receipt.upsert", formValues(event.currentTarget), "Dated supply receipt saved.");
  });
  document.querySelector("#mrp-run-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    void act("mrp.run", formValues(event.currentTarget), "MRP completed and frozen with input/output hashes.");
  });
}

export function renderComputeStudio(nextContext) {
  context = nextContext;
  draw();
}
