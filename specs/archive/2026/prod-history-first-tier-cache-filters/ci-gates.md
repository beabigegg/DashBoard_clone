---
change-id: prod-history-first-tier-cache-filters
schema-version: 0.1.0
last-changed: 2026-05-14
risk: high
tier: 1
---

# CI/CD Gate Plan

Refer to `contracts/ci/ci-gate-contract.md` §1.3.12 for the canonical gate inventory. Entries below cite existing workflows that cover this change; no new workflow file is introduced.

## Local Gates (pre-PR, Tier 0)

```bash
conda run -n mes-dashboard ruff check src/mes_dashboard/
conda run -n mes-dashboard pytest tests/test_common_filters.py tests/test_container_filter_cache.py tests/test_production_history_service.py tests/test_production_history_routes.py tests/test_production_history_sql_runtime.py tests/test_cache_updater_lock_behavior.py tests/routes/test_fuzz_routes.py tests/property/ -v
cd frontend && npm run type-check
cd frontend && npm run test -- production-history && npm run test:legacy
cd frontend && npm run build
cd frontend && npm run css:check
cdd-kit validate --contracts
cdd-kit gate prod-history-first-tier-cache-filters
```

## PR Required Gates (Tier 1, block merge)

| gate | workflow | command | expected |
|---|---|---|---|
| lint | backend-tests.yml | `ruff check .` | exit 0 |
| unit-mock-integration | backend-tests.yml / contract-driven-gates.yml | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` | 3470 pass (28 new) |
| route-fuzz (Tier 1) | backend-tests.yml | `pytest tests/routes/test_fuzz_routes.py -v` | 372 pass (214 new wildcard cases) — PHF-02/PHF-06 meta-char + control-char + multi-`*` + 100-cap → 400 |
| property | backend-tests.yml | `pytest tests/property/ -v` | parser idempotence + cross-filter symmetry |
| frontend-unit | frontend-tests.yml | `npm run test` | 316/316 |
| legacy (node --test) | frontend-tests.yml | `npm run test:legacy` | 251 pass |
| build | frontend-tests.yml | `npm run build` | bundle written to `static/dist/` |
| css-governance | frontend-tests.yml | `npm run css:check` | 0 errors |
| playwright-resilience | e2e-tests.yml | `npx playwright test tests/playwright/resilience/` + `production-history-filter-options-error.spec.ts` | all pass |
| playwright-data-boundary | e2e-tests.yml | `npx playwright test tests/playwright/data-boundary/` | all pass |
| playwright-critical-journeys | e2e-tests.yml | adds 5 new specs (`production-history-cross-filter` / `-wildcard-paste` / `-multi-line-input` / `-pruning-feedback` / `-filter-options-error`) | 10 tests pass |
| contract:validate | contract-driven-gates.yml | `cdd-kit validate --contracts` | All validations passed |

## Informational Gates (Tier 2, non-blocking)

| gate | command | note |
|---|---|---|
| frontend-type-check | `cd frontend && npm run type-check` | informational per ci-contract §1.3.x; 0 errors confirmed |
| mypy | `mypy src/` | not run — env yml does not pin mypy; new public functions are annotated (per backend-engineer log) |

## Nightly Gates (Tier 3)

| gate | command | covers |
|---|---|---|
| nightly-integration | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` | new `test_container_filter_cache_lock_under_4_workers` + `test_lock_holder_crash_releases_lock` (AC-6, PHF-05) against real Oracle XE; new `test_filter_options_falls_back_when_redis_down` + `test_filter_options_l1_fallback` |

## Manual / Weekly Gates (Tier 4)

| gate | trigger | covers |
|---|---|---|
| stress-load | stress-tests.yml weekly / dispatch | `pytest tests/stress/ -m "stress or load"` — cache rebuild thundering herd + high-cardinality LOT IN list (1000 LOTs) |
| empirical close-out | manual (qa-reviewer / release captain) | (a) AC-1 filter-options p95 latency from cache (≤ 100 ms warm); (b) AC-6 multi-worker lock holds under 4 gunicorn workers in staging |

## Promotion Policy

Informational gates (Tier 2) for this change — `frontend-type-check` and `mypy` —
follow the existing ci-contract policy: they stay informational until they hold green
across three consecutive merges touching `frontend/src/production-history/` or
`src/mes_dashboard/services/container_filter_cache.py`, at which point release captain
may promote them to PR-required. This change introduces no new gate eligible for
immediate promotion; the new wildcard route-fuzz coverage is already PR-required (Tier 1).

## Rollback Policy

1. **Schema-version rollback (primary).** Bump `schema_version` in `src/mes_dashboard/services/container_filter_cache.py` from `2` → `3` (or revert to `1`) and deploy. Next L2 read mismatches and forces rebuild under the file lock. **No `redis-cli DEL` required.** Documented under ci-contract §1.3.12.
2. **Code revert.** Changes are additive — `git revert` on the merge commit cleanly reverts service / route / composable / tests. SQL templates unchanged at the structural level (only `_build_extra_filters` composition extended); revert removes new wildcard / MultiSelect predicates cleanly.
3. **Lock-file cleanup.** Post-rollback runbook step: `rm tmp/container_filter_cache.loading` to clear any stale `.loading` sentinel left by a crashed worker (D4 has no mtime reaper — backend-engineer caveat `U4-deferred`).
4. **No Oracle DDL.** No DB-level rollback step.
5. **No spool parquet schema break.** `production_history` spool parquet schema is untouched; existing files remain readable. No `rm tmp/query_spool/production_history_*.parquet` required (cache is Redis-only).
6. **Frontend assets.** `npm run build` after revert regenerates bundles in `src/mes_dashboard/static/dist/`.

## Gate Compatibility Notes

This change introduces new Tier 1 fuzz scope (wildcard meta-char rejection on `mfg_orders[]` / `lot_ids[]` / `wafer_lots[]`) and new multi-worker harness scenarios for `container_filter_cache`. Gate **tiers are unchanged** — both are absorbed by the existing `unit-mock-integration` and `nightly-integration` gates. The cache `schema_version` rollback primitive is a **new contract convention** documented under ci-contract §1.3.12 (patch bump only — gate command/tier/status unchanged). See `contracts/ci/ci-gate-contract.md` §1.3.12 entry "New fuzz + cache rollback coverage — prod-history-first-tier-cache-filters".
