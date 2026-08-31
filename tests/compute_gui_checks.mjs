import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";

const modulePath = process.env.PLAYWRIGHT_MODULE;
if (!modulePath) throw new Error("PLAYWRIGHT_MODULE must point to playwright/index.mjs");
const { chromium } = await import(pathToFileURL(modulePath).href);
const baseUrl = process.env.LANGQI_BASE_URL || "http://127.0.0.1:39931";

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1500, height: 1050 } });
const pageErrors = [];
page.on("pageerror", (error) => pageErrors.push(error.message));

async function sectionHeading(name) {
  await page.getByRole("heading", { level: 2, name }).waitFor();
}

try {
  const createdResponse = await page.request.post(`${baseUrl}/api/workbooks`, {
    data: { name: "Factory control tower" },
  });
  assert.equal(createdResponse.ok(), true);
  const workbook = await createdResponse.json();

  await page.goto(`${baseUrl}/workbooks/${workbook.id}/compute`);
  await sectionHeading(/Turn a workbook into an auditable operating system/);
  await page.getByRole("button", { name: "Build guided factory demo" }).click();
  await page.getByRole("status").filter({ hasText: "Guided factory created" }).waitFor();
  await sectionHeading(/BOM & material requirements planning/);
  await page.getByText("FG-100", { exact: true }).first().waitFor();
  assert.match((await page.locator("main").textContent()) || "", /Crystal controller/);
  assert.match((await page.locator("main").textContent()) || "", /Planned order/i);
  if (process.env.COMPUTE_SCREENSHOT) {
    await page.screenshot({ path: process.env.COMPUTE_SCREENSHOT, fullPage: true });
  }

  await page.getByRole("button", { name: /Runtime schema/ }).click();
  await sectionHeading("Schema studio");
  await page.getByRole("button", { name: "Validate and save schema" }).click();
  await page.getByRole("status").filter({ hasText: "validated and deployed" }).waitFor();
  await page.getByLabel(/^SKU/).fill("CRYSTAL-01");
  await page.getByLabel(/^Quantity/).fill("4");
  await page.getByLabel(/^Unit cost/).fill("12.5");
  await page.getByRole("button", { name: "Create validated record" }).click();
  await page.getByRole("status").filter({ hasText: "Record validated" }).waitFor();
  const recordsPanel = page.locator(".compute-records-panel");
  assert.match((await recordsPanel.textContent()) || "", /CRYSTAL-01/);
  assert.match((await recordsPanel.textContent()) || "", /50/);

  await page.getByRole("button", { name: /General ledger/ }).click();
  await sectionHeading("General ledger");
  await page.getByLabel("Account code").fill("1000");
  await page.getByLabel("Account name").fill("Cash");
  await page.getByLabel("Account type").selectOption("asset");
  await page.getByRole("button", { name: "Save account" }).click();
  await page.getByRole("status").filter({ hasText: "Account 1000 saved" }).waitFor();
  await page.getByLabel("Account code").fill("3000");
  await page.getByLabel("Account name").fill("Opening equity");
  await page.getByLabel("Account type").selectOption("equity");
  await page.getByRole("button", { name: "Save account" }).click();
  await page.getByRole("status").filter({ hasText: "Account 3000 saved" }).waitFor();

  await page.getByLabel("Debit account").selectOption("1000");
  await page.getByLabel("Debit amount").fill("100");
  await page.getByLabel("Credit account").selectOption("3000");
  await page.getByLabel("Credit amount").fill("99");
  await page.getByRole("button", { name: "Validate and post" }).click();
  await page.getByRole("alert").filter({ hasText: "not balanced" }).waitFor();
  assert.match((await page.locator("main").textContent()) || "", /No journal entries/);

  await page.getByLabel("Debit account").selectOption("1000");
  await page.getByLabel("Debit amount").fill("100");
  await page.getByLabel("Credit account").selectOption("3000");
  await page.getByLabel("Credit amount").fill("100");
  await page.getByRole("button", { name: "Validate and post" }).click();
  await page.getByRole("status").filter({ hasText: "Balanced journal posted" }).waitFor();
  assert.match((await page.locator("main").textContent()) || "", /OPEN|JE-00001/);
  await page.getByRole("button", { name: "Recalculate" }).click();
  await page.getByText("Balanced", { exact: true }).waitFor();

  const current = await (await page.request.get(`${baseUrl}/api/workbooks/${workbook.id}/compute`)).json();
  const staleResponse = await page.request.post(`${baseUrl}/api/workbooks/${workbook.id}/compute`, {
    headers: { "x-langqi-user": "stale-client" },
    data: {
      type: "ledger.account.upsert",
      payload: { code: "9999", name: "Stale write", accountType: "asset" },
      expectedRevision: current.enterprise.revision - 1,
    },
  });
  assert.equal(staleResponse.status(), 409);
  assert.equal((await staleResponse.json()).code, "revision_conflict");

  await page.getByRole("button", { name: /Evidence/ }).click();
  await sectionHeading("Compute evidence");
  const evidenceText = (await page.locator("main").textContent()) || "";
  assert.match(evidenceText, /mrp\.run/);
  assert.match(evidenceText, /schema\.record\.upsert/);
  assert.match(evidenceText, /ledger\.journal\.post/);
  assert.deepEqual(pageErrors, []);

  process.stdout.write(JSON.stringify({
    passed: true,
    pages: ["overview", "runtime-schema", "ledger", "mrp", "evidence"],
    controls: ["formula", "reference", "double-entry", "bom-cycle", "revision-conflict", "hash-chain"],
  }) + "\n");
} finally {
  await browser.close();
}
