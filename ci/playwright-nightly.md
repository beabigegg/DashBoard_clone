# Playwright Nightly CI

This document describes the commands used in the nightly CI pipeline for
running integration and end-to-end tests against the MES Dashboard.

## Prerequisites

- The server must be running before any test is invoked.
  Use `./scripts/start_server.sh start` to bring it up.
- Playwright browsers are installed at `~/.cache/ms-playwright/` (shared
  across the host).  Do **not** run `playwright install` in CI — the browsers
  are already there.
- All Python commands must run inside the `mes-dashboard` conda environment.

## Environment variables (set in CI secrets or `.env`)

| Variable | Purpose |
|---|---|
| `E2E_BASE_URL` | Base URL of the running server (default `http://127.0.0.1:8080`) |
| `E2E_USERNAME` | Login username for E2E tests (falls back to `LOCAL_AUTH_USERNAME`) |
| `E2E_PASSWORD` | Login password for E2E tests (falls back to `LOCAL_AUTH_PASSWORD`) |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` | Path to Chromium binary if not auto-detected |

## Nightly command

```bash
# 1. Run backend integration + e2e tests (pytest-based)
conda run -n mes-dashboard pytest --run-integration --run-e2e tests/ -v

# 2. Run Playwright browser tests
cd frontend && npx playwright test
```

## Running individual suites

```bash
# Backend unit tests only (no server required)
conda run -n mes-dashboard pytest tests/ -v

# Backend integration tests (requires DB)
conda run -n mes-dashboard pytest tests/ -v --run-integration

# Playwright tests only
cd frontend && npx playwright test

# Single spec
cd frontend && npx playwright test tests/playwright/hold-overview.spec.js

# Headed mode for local debugging
cd frontend && npx playwright test --headed --project=chromium
```

## Artefacts

- Screenshots and videos for failed tests: `frontend/test-results/`
- HTML report: `frontend/playwright-report/index.html`
  Open with: `cd frontend && npx playwright show-report`
