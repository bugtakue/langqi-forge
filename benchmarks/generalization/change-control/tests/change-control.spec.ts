import { expect, test } from "@playwright/test";

const summary = "Rotate signing key in the edge gateway";

test.describe.serial("unseen change-control domain", () => {
  test("renders the required semantic change form", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Change Control" })).toBeVisible();
    await expect(page.getByLabel("Requester")).toBeVisible();
    await expect(page.getByLabel("Change summary")).toBeVisible();
    await expect(page.getByLabel("Risk")).toHaveValue("Low");
    await expect(page.getByRole("button", { name: "Submit change" })).toBeEnabled();
  });

  test("rejects a blank request without creating a record", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Requester").fill("   ");
    await page.getByLabel("Change summary").fill(" ");
    await page.getByRole("button", { name: "Submit change" }).click();
    await expect(page.getByText("Requester and summary are required", { exact: true })).toBeVisible();
    await expect(page.getByRole("article")).toHaveCount(0);
  });

  test("creates arbitrary persistent pending requests", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Requester").fill("Alice");
    await page.getByLabel("Change summary").fill(summary);
    await page.getByLabel("Risk").selectOption("High");
    await page.getByRole("button", { name: "Submit change" }).click();
    const request = page.getByRole("article", { name: summary });
    await expect(request).toContainText("Requester: Alice");
    await expect(request).toContainText("Risk: High");
    await expect(request).toContainText("Status: Pending");
    await expect(request.getByRole("button", { name: "Execute" })).toBeDisabled();
    await page.reload();
    await expect(page.getByRole("article", { name: summary })).toContainText("Status: Pending");
  });

  test("rejects self approval and accepts an independent reviewer", async ({ page }) => {
    await page.goto("/");
    const request = page.getByRole("article", { name: summary });
    await request.getByLabel("Reviewer").fill("aLiCe");
    await request.getByRole("button", { name: "Approve" }).click();
    await expect(request).toContainText("Reviewer must differ from requester");
    await expect(request).toContainText("Status: Pending");
    await request.getByLabel("Reviewer").fill("Bob");
    await request.getByRole("button", { name: "Approve" }).click();
    await expect(request).toContainText("Status: Approved");
    await expect(request).toContainText("Approved by: Bob");
    await expect(request.getByRole("button", { name: "Execute" })).toBeEnabled();
  });

  test("executes once and preserves the terminal state after refresh", async ({ page }) => {
    await page.goto("/");
    const request = page.getByRole("article", { name: summary });
    await request.getByRole("button", { name: "Execute" }).click();
    await expect(request).toContainText("Status: Executed");
    await page.reload();
    const reopened = page.getByRole("article", { name: summary });
    await expect(reopened).toContainText("Status: Executed");
    await expect(reopened).toContainText("Requester: Alice");
    await expect(reopened).toContainText("Risk: High");
    await expect(reopened).toContainText("Approved by: Bob");
  });
});
