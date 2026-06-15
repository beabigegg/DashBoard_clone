# Change Request

## Original Request

Fix all 21 failing Playwright E2E specs across 6 root-cause groups:
- Group A (5): `production-history-multi-line-input` + `production-history-wildcard-paste` — `button:has-text("查詢").first()` picks Tab A tab button (substring match) instead of the submit button `[data-testid="ph-query-btn"]`
- Group B (2): `job-abandon-on-unload` + `resilience/browser-history:165` — raw `page.click('a[href*="..."]')` without opening sidebar first; sidebar starts closed by default
- Group C (2): `hold-history-flat-table` 202 async path tests — missing `loginViaApi`, uses hash-based URL `portal-shell.html#/hold-history` that bypasses auth
- Group D (4): `wip-matrix-drilldown` — `navigateViaSidebar` stubs WIP API with empty data, `waitForSelector: 'table'` never resolves because matrix doesn't render without data
- Group E (1): `production-history-pruning-feedback` — `waitForResponse(filter-options)` registered after initial mount call already completed
- Group F (7): `reject-history` + `reject-material-flat-table` — no API mocks, depend on live Oracle; need full mock conversion (Oracle is available in dev but tests must be self-contained)

## Business / User Goal

All 133 E2E specs should pass reliably in CI without depending on Oracle availability. Currently 21 specs fail due to spec bugs and missing mocks.

## Non-goals

- No production code changes (only spec files under `tests/playwright/`)
- No new features or UI changes

## Constraints

- Oracle is available in the current dev environment
- Do not run `playwright install` (browsers in `~/.cache/ms-playwright/`)
- Must not commit `.env`

## Known Context

Full root-cause analysis completed. Exact line numbers and error messages confirmed from a full suite run (109 passed, 21 failed, 3 skipped, 31 min).

## Open Questions

None.

## Requested Delivery Date / Priority

High — these block CI green.
