# CI/CD Gate Plan

## Change ID
migrate-production-history-ts

## Required Gates
| gate | tier | required | trigger | command/workflow | expected artifact |
|---|---:|---:|---|---|---|
| type-check | 1 | yes | pull_request | `cd frontend && npm run type-check` (vue-tsc --noEmit) | console exit 0 |
| build | 1 | yes | pull_request | `cd frontend && npm run build` | `src/mes_dashboard/static/dist/*` bundle |
| vitest | 1 | yes | pull_request | `cd frontend && npm run test` | console: 302 passed (30 files) |
| pytest:production-history | 1 | yes | pull_request | `pytest tests/test_production_history_*.py` | console: 62 passed |
| pytest:parity | 1 | yes | pull_request | `pytest tests/test_frontend_compute_parity.py tests/test_frontend_duckdb_parity.py tests/test_job_query_frontend_safety.py` | console: 10 passed |
| css:check | 1 | yes | pull_request | `cd frontend && npm run css:check` | console: 0 errors |
| contract | 1 | n/a | pull_request | n/a — no contract surface change | n/a |
| integration | 1/3 | n/a | pull_request | covered by pytest:production-history (route+service+sql+job+async) | n/a |
| e2e-critical | 1 | n/a | pull_request | existing `tests/e2e/test_production_history_e2e.py` retained as regression coverage; not run on PR | n/a |
| visual | 2 | n/a | pull_request | no UI design change | n/a |
| data-boundary | 1 | n/a | pull_request | no data shape change | n/a |
| resilience | 1 | yes | pull_request | included in vitest run (`production-history-abort.test.js`) | console: 7/7 passed |
| fuzz/monkey | 1/3 | n/a | n/a | not applicable for type-annotation-only change | n/a |
| stress | 4/5 | n/a | weekly | not applicable | n/a |
| soak | 4/5 | n/a | weekly | not applicable | n/a |

## New Workflow Changes
None. This change uses existing CI workflows (`.github/workflows/`) without modification. The existing `npm run type-check` + `npm run build` + `pytest` steps already cover this migration's surface.

## Required Check Policy
All gates marked `required: yes` above must pass on the PR before merge:
- type-check (vue-tsc)
- build (Vite)
- vitest (302 tests)
- pytest:production-history (62 tests)
- pytest:parity (10 tests)
- css:check

A failed gate blocks merge. No bypass mechanism for this change.

## Informational Gate Promotion Policy
N/A — no new gates introduced; no informational gates require promotion. The existing E2E (`test_production_history_e2e.py`) remains nightly/manual.

## Rollback Policy
If a regression is discovered post-merge:
1. Revert the merge commit (single commit covering all .js → .ts renames).
2. The `.ts` files preserve identical runtime behavior to the `.js` originals (verified by zero behavior change criterion), so revert should be no-op for runtime.
3. Re-deploy via standard deploy workflow.

No data migration, no schema change, no Redis cache invalidation needed.

## Artifact Retention
- Built dist bundle: standard CI retention (existing policy)
- Test result XMLs: standard CI retention
- No new artifacts produced by this change

## Merge Eligibility Decision
**Local gate verification (2026-05-14, pre-PR):**
- ✅ `npm run type-check` — 0 errors
- ✅ `npm run build` — built in 15.88s, all entries bundled including `production-history.js`
- ✅ `npm run test` — 302/302 passed (30 files)
- ✅ `pytest tests/test_production_history_*.py` — 62/62 passed
- ✅ `pytest tests/test_frontend_*_parity.py tests/test_job_query_frontend_safety.py` — 10/10 passed
- ✅ `npm run css:check` — 0 errors, 47 warnings (pre-existing, unrelated)

**Eligible for PR submission.** All required pre-merge gates are green locally.
