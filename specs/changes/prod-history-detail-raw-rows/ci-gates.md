# CI/CD Gate Plan

## Change ID
prod-history-detail-raw-rows

## Required Gates
| gate | tier | required | trigger | command/workflow | expected artifact |
|---|---:|---:|---|---|---|
| type-check | 1 | yes | pull_request | `cd frontend && npm run type-check` (vue-tsc --noEmit) | console exit 0 |
| build | 1 | yes | pull_request | `cd frontend && npm run build` | `src/mes_dashboard/static/dist/*` bundle |
| vitest | 1 | yes | pull_request | `cd frontend && npm run test` | console: 302 passed (30 files) |
| pytest:production-history | 1 | yes | pull_request | `pytest tests/test_production_history_*.py` | console: 75 passed (62 pre-existing + 13 new sql_runtime tests) |
| pytest:parity-safety | 1 | yes | pull_request | `pytest tests/test_frontend_compute_parity.py tests/test_frontend_duckdb_parity.py tests/test_job_query_frontend_safety.py` | console: 10 passed |
| css:check | 1 | yes | pull_request | `cd frontend && npm run css:check` | console: 0 errors |
| contract:validate | 1 | yes | pull_request | `cdd-kit validate --contracts` | console: All validations passed |
| e2e-critical | 1 | no | nightly | `tests/e2e/test_production_history_e2e.py` (multi-partial container) | retained as regression coverage; not blocking PR |
| stress | 2 | manual | qa-reviewer | production-history stress test (one-shot during qa-reviewer) | qa-report.md records parquet size delta + p95 latency delta |
| data-boundary | 1 | yes | pull_request | included in pytest:production-history (month-boundary partial attribution) | console passed |
| resilience | 1 | yes | pull_request | included in vitest (`production-history-abort.test.js`) | console: 7/7 passed |
| visual | 2 | n/a | n/a | no UI design change (Non-goals forbid component structure change) | n/a |
| fuzz/monkey | 1/3 | n/a | n/a | not applicable for SQL row-grain change | n/a |
| soak | 4/5 | n/a | weekly | not applicable | n/a |

## New Workflow Changes
None. Existing CI workflows (`.github/workflows/`) cover all required gates. The new 13 sql_runtime tests added by backend-engineer are picked up automatically by the existing `pytest tests/test_production_history_*.py` glob.

## Required Check Policy
All gates marked `required: yes` must pass on the PR before merge:
- type-check (vue-tsc)
- build (Vite)
- vitest (302 tests)
- pytest:production-history (75 tests)
- pytest:parity-safety (10 tests)
- css:check
- contract:validate

Stress test is a manual one-shot gate executed during qa-reviewer phase; results recorded in `qa-report.md` (not enforced on PR by CI).

## Informational Gate Promotion Policy
N/A — no new gates introduced. Existing E2E (`test_production_history_e2e.py`) remains nightly/manual coverage.

## Rollback Policy
If a regression is discovered post-merge:
1. Revert the merge commit covering SQL + service + frontend changes.
2. Re-deploy via standard deploy workflow.
3. **Contract rollback**: `contracts/data/data-shape-contract.md` §3.4 and `contracts/business/business-rules.md` PH-01..PH-04 must be reverted in lockstep (both are additive — revert is a clean removal).
4. **Spool invalidation**: existing spool parquet files under `tmp/query_spool/production_history_*` must be cleared (their schema no longer matches the reverted SQL). Operationally: delete `tmp/query_spool/production_history_*.parquet` after revert; users will re-trigger queries which regenerate spool against the old schema.

No data migration, no Oracle schema change.

## Artifact Retention
- Built dist bundle: standard CI retention
- Test result XMLs: standard CI retention
- qa-report.md (parquet size + latency deltas): retained in archive under `specs/archive/2026/`

## Merge Eligibility Decision
**Local gate verification (2026-05-14, pre-PR):**
- ✅ `npm run type-check` — 0 errors
- ✅ `npm run build` — 15.07s
- ✅ `npm run test` — 302/302
- ✅ `pytest tests/test_production_history_*.py` — 75/75
- ✅ `pytest tests/test_frontend_*_parity.py tests/test_job_query_frontend_safety.py` — 10/10
- ✅ `npm run css:check` — 0 errors
- ✅ `cdd-kit validate --contracts` — All validations passed

**Eligible for PR submission pending qa-reviewer + stress test record.**
