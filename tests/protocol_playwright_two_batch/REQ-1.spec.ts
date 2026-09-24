import { expect, test } from '@playwright/test';

// Fixed protocol fixture only. These tests do not measure a real coding model.
test('REQ-1: first batch behavior remains functional', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Example' })).toBeVisible();
  await page.getByRole('button', { name: 'Try' }).click();
  await expect(page.locator('#status')).toHaveText('Clicked');
});
