---
change-id: migrate-query-tool-ts
schema-version: 0.1.0
last-changed: 2026-05-14
risk: low
tier: 2
---

# Test Plan: migrate-query-tool-ts

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 (9 JS files renamed to .ts) | static / file audit | shell `find frontend/src/query-tool -name '*.js'` post-migration | pre-merge |
| AC-2 (`npm run type-check` exits 0) | type-check gate | `frontend/tsconfig.json` (vue-tsc --noEmit) | pre-merge |
| AC-3 (existing frontend tests pass) | unit (Vitest + node:test) | see §Test Files | pre-merge |
| AC-4 (Python tests pass) | safety | `tests/test_job_query_frontend_safety.py` | pre-merge |
| AC-5 (SFCs use `<script lang="ts">`) | static / file audit | grep `<script>` without `lang="ts"` in `frontend/src/query-tool/**/*.vue` | pre-merge |
| AC-6 (no runtime regressions) | e2e | `frontend/tests/playwright/query-tool.spec.js`, `query-tool-url-state.spec.js` | informational (nightly) |

## Test Families Required

unit, static/file-audit, safety (pytest), e2e (informational)

## Test Files

### Legacy node:test — `npm run test:legacy` (pre-merge)

`frontend/tests/legacy/query-tool-composables.test.js`
- `useLotResolve validates multi-query size and resolves deduplicated inputs`
- `useLotLineage deduplicates in-flight lineage requests and stores graph data`
- `useEquipmentQuery performs timeline multi-query and keeps validation errors user-friendly`
- `useLotDetail single-item mode captures quality_meta from response and clears on complete status`
- `useLotDetail single-item association captures quality_meta for paged tabs`
- `useLotDetail batches selected container ids and preserves workcenter filters in follow-up query`
- `useLotDetail changing per-page resets current page to 1 for paged tabs`

### Vitest unit — `npm run test` (pre-merge)

`frontend/tests/query-tool/App.url-state.test.js`
- `Query Tool App URL state > restores reverse deep-link state from URL on mount`
- `Query Tool App URL state > syncs reverse workcenter groups back into runtime URL`
- `Query Tool App URL state > restores equipment deep-link state from URL on mount`
- `Query Tool App URL state > syncs lot-equipment state back into runtime URL`

`frontend/tests/query-tool/useLotDetail.pagination.test.js`
- `useLotDetail pagination > resets page to 1 when per-page changes for history and materials tabs`

`frontend/tests/abort/query-tool-abort.test.js`
- `query-tool abort — useRequestGuard invalidation on unmount > nextRequestId on unmount marks any captured request id as stale`
- `query-tool abort — useRequestGuard invalidation on unmount > response arriving after unmount-triggered nextRequestId is dropped`
- `query-tool abort — useLotResolve loading state cleanup > loading.resolving returns to false after a failed request`
- `query-tool abort — useLotResolve loading state cleanup > loading.resolving returns to false after successful request`
- `query-tool abort — no stale state mutation (abort then settle) > AbortController abort causes pending fetch to reject`
- `query-tool abort — no stale state mutation (abort then settle) > abort on an already-settled promise is a no-op`

### Python safety — `pytest tests/test_job_query_frontend_safety.py` (pre-merge)

Audit `tests/test_job_query_frontend_safety.py` for hardcoded `.js` extension references to
`query-tool/` files before running; update any such paths to `.ts`.

### E2E Playwright — informational (nightly only)

`frontend/tests/playwright/query-tool.spec.js`
`frontend/tests/playwright/query-tool-url-state.spec.js`

### Manual smoke (post-deploy)

Open query-tool page, run a lot trace and an equipment query, confirm results render without JS console errors.

## Tier Summary

| tier | when | commands |
|---|---|---|
| pre-merge | every commit, required to pass | `npm run type-check`, `npm run test`, `npm run test:legacy`, `pytest tests/test_job_query_frontend_safety.py` |
| informational | nightly / post-deploy | Playwright E2E specs above |
| manual | post-deploy | browser smoke of lot trace + equipment query |

## Out of Scope

- Backend API tests — no backend changes
- Contract validator (`cdd-kit validate`) — no contract changes
- CSS governance check (`npm run css:check`) — no style changes
- Performance / stress / soak testing — pure rename, no logic change
- Visual regression testing — no UI changes
- `index.html` `./main.js` entry — intentionally not changed (Vite resolves `.ts` at build time; project-wide convention)
- Static `vi.mock('...file.js')` calls in Vitest — Vite mock resolution handles `.js` → `.ts` transparently; no update needed

## Notes

`App.url-state.test.js` and `query-tool-abort.test.js` both use static `vi.mock('...file.js')` specifiers
against query-tool composables. Per CLAUDE.md migration rules these must NOT be updated to `.ts`.
`useLotDetail.pagination.test.js` imports `useLotDetail.js` directly; Vite resolves `.ts` transparently.
The legacy node:test runner uses `ts-resolver-loader.mjs` which handles `.js` specifiers pointing at `.ts` files.
