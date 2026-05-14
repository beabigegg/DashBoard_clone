---
change-id: migrate-production-history-ts
status: closed
closed-on: 2026-05-14
tier: 3
---

# Archive: migrate-production-history-ts

## Change Summary

Phase 3 per-app TypeScript migration of `frontend/src/production-history/`. Pure type-annotation conversion with strictly zero runtime behavior change. This is the 6th Phase 3 module to follow the established pattern (after `reject-history`, `hold-history`, `qc-gate`, `resource-status`, `job-query`).

## Final Behavior

No user-visible or runtime behavior change. Static type-check surface expanded to cover production-history sources; identical bundle output and identical API/cache/SQL behavior.

## Final Contracts Updated

None. `contract-reviewer` (agent-log/contract-reviewer.yml) confirmed no API / data / env / business-logic / CSS / CI contract surface was touched.

## Final Tests Added / Updated

- `frontend/tests/abort/production-history-abort.test.js` — 4 dynamic `import('.../useProductionHistory.js')` specifiers dropped `.js` extension (Phase 3 audit per CLAUDE.md rule).
- No new tests added; existing coverage retained:
  - Vitest: 302/302 (30 files, including 7/7 production-history abort tests)
  - pytest production-history: 62/62 (routes, service, sql-runtime, job-service, async-routes)
  - pytest parity/safety: 10/10 (frontend_compute_parity, frontend_duckdb_parity, job_query_frontend_safety)

## Final CI/CD Gates

All required pre-merge gates passed locally and on CI (commit 02688ee):
- `npm run type-check` (vue-tsc --noEmit) — 0 errors
- `npm run build` (Vite) — 15.88 s, production-history bundled
- `npm run test` (Vitest) — 302/302
- `pytest tests/test_production_history_*.py` — 62/62
- `pytest tests/test_frontend_*_parity.py tests/test_job_query_frontend_safety.py` — 10/10
- `npm run css:check` — 0 errors

No new CI workflows required.

## Production Reality Findings

No surprises. Pattern matched the prior 5 Phase 3 migrations exactly. `index.html` was correctly left unchanged (Vite resolves `main.ts` from `./main.js` reference — already documented in CLAUDE.md from `reject-history-ts`). Abort-test specifier audit was the only required test edit.

## Lessons Promoted to Standards

None. The migration was a textbook application of the established Phase 3 pattern. Every applicable rule already lives in `CLAUDE.md` under TypeScript Migration Rules from prior migrations:

- `index.html` left unchanged — already documented from `reject-history-ts`
- Abort-test `.js` specifier audit (drop `.js` rather than rewriting to `.ts`) — already documented from `migrate-shared-ui-ts`
- Python parity/safety test path audit on `.js → .ts` rename — already documented from `migrate-job-query-ts`
- tsconfig include path expansion per Phase 3 module — implicit standard practice from prior 5 migrations

Task `7.2` marked `skipped` in tasks.yml with this rationale.

## Follow-up Work

- **Change 2 (`prod-history-detail-raw-rows`)**: scaffolded but not yet implemented. Removes GROUP BY aggregation from detail data to show raw rows. Depends on this change.
- **Change 3 (`prod-history-first-tier-cache-filters`)**: scaffolded but not yet implemented. Promotes Package/BOP/PJ_FUNCTION (low cardinality, full-list cache) and 工單號/LOT ID/Wafer LOT (high cardinality, multi-line + `*` wildcard input) to first-tier filters. Depends on Change 2.
- Pre-existing cosmetic: `frontend/tests/legacy/production-history.test.js:4` docstring still mentions `useProductionHistory.js`. Not blocking; can be updated in a future cleanup pass.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`).
