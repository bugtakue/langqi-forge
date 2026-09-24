import { expect, test } from '@playwright/test';

// Fixed protocol fixture only. These tests do not measure a real coding model.
test('REQ-2: second batch module works after refresh', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Second' }).click();
  await expect(page.locator('#status')).toHaveText('Ready');
  await page.reload();
  await page.getByRole('button', { name: 'Second' }).click();
  await expect(page.locator('#status')).toHaveText('Ready');
});
