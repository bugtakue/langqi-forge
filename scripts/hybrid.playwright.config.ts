import { defineConfig } from '@playwright/test';

// Diagnostic bridge for a current-base generated app in an arm64 browser.
// The official current Runner and its hidden tests are not involved.
export default defineConfig({
  testDir: '.',
  timeout: 10000,
  expect: { timeout: 10000 },
  fullyParallel: false,
  workers: 4,
  reporter: [['json', { outputFile: process.env.FACTORY26_HYBRID_REPORT }]],
  use: {
    baseURL: 'http://127.0.0.1:3000',
    channel: 'chromium',
    trace: 'off',
    screenshot: 'off',
  },
});
