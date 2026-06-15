import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/playwright',
  timeout: 60_000,
  retries: 1,
  workers: process.env.PW_WORKERS ? parseInt(process.env.PW_WORKERS) : 1,
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:8080',
    headless: true,
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // Point Playwright to the shared browser cache so we never call
        // `playwright install` in CI (browsers live in ~/.cache/ms-playwright).
        executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
      },
    },
  ],
  // Output folder for test artefacts (screenshots, videos, traces)
  outputDir: './test-results',
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
});
