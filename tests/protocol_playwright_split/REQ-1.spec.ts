import { expect, test } from '@playwright/test';

// Fixed protocol fixture only; not a real coding-model score.
test('REQ-1 and REQ-2: salvaged half remains interactive', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Salvaged' })).toBeVisible();
  await page.getByRole('button', { name: 'Try' }).click();
  await expect(page.locator('#status')).toHaveText('Clicked');
});
