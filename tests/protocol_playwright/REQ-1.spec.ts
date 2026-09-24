import { expect, test } from '@playwright/test';

// Launcher/evaluation plumbing only. The protocol gateway emits this heading;
// passing this test says nothing about a real-model BookStack/Keep result.
test('REQ-1: protocol fixture heading renders in the browser', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Example' })).toBeVisible();
});
