import { defineConfig, devices } from '@playwright/test';
import { createRequire } from 'module';
import { readFileSync } from 'fs';
import { resolve } from 'path';

// Load project-root .env so LOCAL_AUTH_USERNAME / LOCAL_AUTH_PASSWORD reach
// _auth.js loginViaApi.  Use manual parsing to avoid a dotenv dependency;
// only sets vars not already present (so real env vars in CI always win).
try {
  const envPath = resolve(createRequire(import.meta.url).resolve('./package.json'), '../../.env');
  const lines = readFileSync(envPath, 'utf8').split('\n');
  for (const line of lines) {
    const m = line.match(/^([A-Z_][A-Z0-9_]*)=(.*)$/);
    if (m && !(m[1] in process.env)) {
      process.env[m[1]] = m[2].replace(/^(['"])(.*)\1$/, '$2');
    }
  }
} catch {
  // .env absent — CI uses real env vars
}

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
        // Must be under launchOptions, not top-level `use` -- a top-level
        // `use.executablePath` is a no-op (verified against a real host
        // browser-version mismatch: the driver still resolves its own
        // default headless-shell build and ignores this field entirely).
        launchOptions: {
          executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
        },
      },
    },
  ],
  // Output folder for test artefacts (screenshots, videos, traces)
  outputDir: './test-results',
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
});
