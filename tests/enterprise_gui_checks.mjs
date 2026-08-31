import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";

const modulePath = process.env.PLAYWRIGHT_MODULE;
if (!modulePath) throw new Error("PLAYWRIGHT_MODULE must point to playwright/index.mjs");
const { chromium } = await import(pathToFileURL(modulePath).href);
const baseUrl = process.env.LANGQI_BASE_URL || "http://127.0.0.1:39921";

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.on("pageerror", (error) => {
  throw error;
});

async function heading(expected) {
  await page.locator("h1").first().waitFor();
  assert.match((await page.locator("h1").first().textContent()) || "", expected);
}

try {
  const initialState = await (await page.request.get(`${baseUrl}/api/state`)).json();
  const owner = initialState.organizations.find((entry) => entry.name === "acme").owner;
  const reviewer = initialState.environments.find((entry) => entry.repoId === "acme/pr-repo" && entry.name === "production").requiredReviewers[0];
  await page.goto(`${baseUrl}/login`);
  await page.getByLabel("Username or email").fill(owner);
  await page.getByLabel("Password").fill("Fixture-password-123!");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL(`${baseUrl}/`);

  await page.goto(`${baseUrl}/acme/pr-repo/actions`);
  await heading(/^Actions$/);
  await page.getByRole("link", { name: "CI", exact: true }).click();
  await heading(/^CI$/);
  await page.getByRole("button", { name: "Run workflow", exact: true }).click();
  await page.waitForURL(/\/actions\/runs\//);
  await heading(/Workflow run #/);
  assert.match((await page.locator("main").textContent()) || "", /waiting/i);

  await page.evaluate((user) => localStorage.setItem("langqi-forge-session", user), reviewer);
  await page.reload();
  await page.getByRole("button", { name: "Approve deployment" }).click();
  await page.waitForFunction(() => document.querySelector("main")?.textContent?.includes("success"));

  await page.evaluate((user) => localStorage.setItem("langqi-forge-session", user), owner);
  await page.goto(`${baseUrl}/acme/pr-repo/settings/rules`);
  await heading(/Repository rulesets/);
  assert.match((await page.locator("main").textContent()) || "", /Main branch guard/);

  await page.goto(`${baseUrl}/acme/issues-repo/issues/templates`);
  await heading(/Issue forms/);
  await page.getByRole("link", { name: "Use template" }).first().click();
  await heading(/Bug report/);
  await page.getByLabel("Title").fill("Enterprise form UI works");
  await page.getByLabel("Reproduction steps").fill("Open the enterprise issue form");
  await page.getByLabel("Expected behavior").fill("The structured issue is created");
  await page.getByLabel("Severity").selectOption("High");
  await page.getByLabel("I searched existing issues").check();
  await page.getByRole("button", { name: "Submit new issue" }).click();
  await page.waitForURL(/\/issues\/\d+$/);
  await heading(/Enterprise form UI works/);

  await page.goto(`${baseUrl}/orgs/acme/settings/security`);
  await heading(/Authentication security/);
  await page.getByLabel("Enable SAML SSO").check();
  await page.getByLabel("Enable SCIM provisioning").check();
  await page.getByLabel("Identity provider sign-on URL").fill("https://idp.example.test/sso");
  await page.getByLabel("Issuer").fill("https://idp.example.test/");
  await page.getByLabel("Public certificate").fill("test-public-certificate");
  await page.getByRole("button", { name: "Save authentication settings" }).click();
  await page.getByText("Authentication settings saved.").waitFor();

  await page.goto(`${baseUrl}/orgs/acme/settings/scim`);
  await heading(/SCIM provisioning/);
  await page.getByLabel("Username").fill("managed-ui-user");
  await page.getByLabel("Display name").fill("Managed UI User");
  await page.getByLabel("Email").fill("managed-ui@example.test");
  await page.getByRole("button", { name: "Provision with SCIM" }).click();
  await page.getByText("managed-ui-user", { exact: true }).waitFor();

  await page.goto(`${baseUrl}/orgs/acme/settings/data-policies`);
  await heading(/Fine-grained data policies/);
  await page.getByLabel("Name").fill("UI policy");
  await page.getByLabel("Dataset").fill("customer-records");
  await page.getByLabel("Users or teams").fill(owner);
  await page.getByLabel("Row scope field").fill("department");
  await page.getByLabel("Allowed row values").fill("research");
  await page.getByLabel("Hidden fields").fill("salary");
  await page.getByRole("button", { name: "Create data policy" }).click();
  await page.getByText("UI policy", { exact: true }).waitFor();

  await page.goto(`${baseUrl}/orgs/acme/audit-log`);
  await heading(/^Audit log$/);
  await page.getByRole("button", { name: "Verify chain" }).click();
  await page.getByText(/Chain verified:/).waitFor();
  assert.match((await page.locator("main").textContent()) || "", /workflow\.dispatch/);

  process.stdout.write(JSON.stringify({
    passed: true,
    pages: ["actions", "workflow-run", "rulesets", "issue-forms", "saml", "scim", "data-policies", "audit"],
  }) + "\n");
} finally {
  await browser.close();
}
