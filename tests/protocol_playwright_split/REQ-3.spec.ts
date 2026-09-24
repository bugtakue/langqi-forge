import { expect, test } from '@playwright/test';

// Intentionally fails: the second half is never implemented by the fixture.
test('REQ-3: failed half has no false implementation credit', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Third' })).toBeVisible();
});
