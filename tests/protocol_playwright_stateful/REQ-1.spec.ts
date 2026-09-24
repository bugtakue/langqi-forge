import { expect, test } from '@playwright/test';

// Fixed-response protocol fixture: this tests probe isolation, not model skill.
test('REQ-1: independent evaluation starts from the untouched seed', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Example' })).toBeVisible();
  const initial = await page.request.get('/api/state');
  expect(await initial.json()).toEqual({ count: 0 });
  await page.getByRole('button', { name: 'Increment' }).click();
  await expect(page.getByText('Count: 1')).toBeVisible();
  const updated = await page.request.get('/api/state');
  expect(await updated.json()).toEqual({ count: 1 });
});
