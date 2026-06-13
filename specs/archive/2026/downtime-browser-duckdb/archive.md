# Archive: downtime-browser-duckdb

> **Cold Data Warning**: This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`).

## Change Summary

Relocated downtime-analysis compute (cross-shift merge, job-bridge join, taxonomy building) from Python backend to DuckDB-WASM in the browser. The server now writes two raw parquet spools (`downtime_analysis_base_events`, `downtime_analysis_job_bridge`) and returns spool URLs; the browser runs all aggregation via DuckDB-WASM. A `DOWNTIME_BROWSER_DUCKDB` feature flag gates the new path; the legacy server-side enriched-spool path is preserved behind `flag=false`. This eliminates the gunicorn OOM risk on wide (>90d) queries that required the former `_MAX_ORACLE_DAYS=90` hard cap.

## Final Behavior

- `POST /api/downtime-analysis/query` with `DOWNTIME_BROWSER_DUCKDB=true` returns `{base_spool_url, jobs_spool_url, query_id, taxonomy, schema_version}` — no pre-computed summary/daily_trend/big_category/top_reasons.
- `useDowntimeDuckDB.ts` fetches both parquets, runs DuckDB-WASM compute, and feeds App.vue KPI cards, charts, and tables. All filter interactions (`handleCategoryClick`, `handleStatusClick`, `handleGranularityChange`) recompute via DuckDB without round-trips to the server (AC-5).
- `DOWNTIME_BROWSER_DUCKDB=false` (default) restores the prior legacy path with zero code deletion — the enriched-spool approach remains functional as rollback safety net.
- `_MAX_ORACLE_DAYS` constant removed; 180-day queries are now permitted.

## Final Contracts Updated

| Contract | Version Change | Nature |
|---|---|---|
| `api-contract.md` | 1.14.0 → 1.15.0 | New `/query` response shape + deprecated enriched-spool endpoints |
| `api-inventory.md` | 1.1.13 → 1.2.0 | New endpoints: `/query` (new shape), `/spool/downtime_analysis_base_events/…`, `/spool/downtime_analysis_job_bridge/…` |
| `data-shape-contract.md` | 1.12.3 → 1.13.0 | §3.13: base_events + job_bridge raw parquet schemas |
| `business-rules.md` | 1.16.0 → 1.17.0 | DA-01..DA-04 locus updates + new DA-09..DA-12 (SCHEMA_VERSION, atomicity, taxonomy) |
| `env-contract.md` | 1.0.6 → 1.0.7 | `DOWNTIME_BROWSER_DUCKDB` feature flag (default `false`) |
| `ci-gate-contract.md` | 1.3.19 → 1.3.20 | New Playwright spec gate + OOM-risk rollback caveat |

## Final Tests Added / Updated

| File | Tests | Covers |
|---|---|---|
| `tests/test_downtime_analysis_routes.py` | +`TestQueryRoute` (12), +`TestQueryRouteContract`, +`TestMaxOracleDaysRemoved` | AC-1, AC-6 |
| `tests/test_downtime_analysis_service.py` | +`TestRawSpoolWriter` (5), +`TestTaxonomyBuilder` (6), +`TestTwoParquetAtomicity`, +`TestDataBoundary` (7) | AC-2, AC-4, AC-7 |
| `frontend/src/downtime-analysis/__tests__/useDowntimeDuckDB.test.ts` | 812 lines, 31 tests | AC-3, AC-4, AC-5, AC-8 |
| `frontend/tests/playwright/downtime-analysis.spec.ts` | 937 lines, 17 tests (migrated .spec.js → .spec.ts) | AC-5, AC-6, AC-7, AC-8 |
| `tests/e2e/test_downtime_analysis_e2e.py` | +`TestDowntimeQueryNewShape` (6), +`TestTwoParquetAtomicityRoute`, +`TestFeatureFlagFallback` | AC-1, AC-7 |
| `tests/stress/test_downtime_analysis_stress.py` | New stress file | AC-7 OOM elimination |
| `tests/integration/test_rowcount_flag_parity.py` | Updated 2 tests for date-range parallel chunking | ADR-0003 contract maintenance |

## Final CI/CD Gates

Tier 1 required: `unit-mock-integration`, `frontend-unit`, `css-governance`, `frontend-type-check`, `downtime-playwright-e2e`, `contract-validate`.
Tier 3 required (nightly): `nightly-parity-regression` (184k-row fixture).
Tier 4 (weekly): `stress-oom-elimination`, `soak-memory-stable`.
Tier 5 (pre-prod manual): `manual-flag-rollback`.

## Production Reality Findings

- 4 pre-existing e2e failures in `tests/e2e/test_downtime_analysis_e2e.py` were identified: 3 patched `load_downtime_events` at the wrong module (service instead of cache definition site); 1 exposed a real `ProcessLevelCache.delete()` → `.invalidate()` bug which was fixed in this change. These failures existed before the change (confirmed on baseline commit `971bb8e`).
- Commit `971bb8e` (parallel date-range chunking, added after test-plan was finalized) required updating 2 tests in `test_rowcount_flag_parity.py` to reflect the new `chunk_start`/`chunk_end` key names and parallel=`_DOWNTIME_ENGINE_PARALLEL` default. ADR-0003's core constraint (no row-count `start_row` chunks) was preserved.
- Taxonomy label discrepancy: backend uses `'改機換料'`/`'治工具更換與模具清潔'`; frontend `useBigCategory.ts` uses `'換型換線'`/`'換刀清模'`. The composable uses server-authoritative taxonomy (design.md D5); deployment runbook should note stale-bookmark 0-row-filter risk.
- `_ALLOWED_NAMESPACES` in `spool_routes.py` required explicit addition of `downtime_analysis_base_events` and `downtime_analysis_job_bridge` — omission would have caused HTTP 400 on all parquet downloads.

## Lessons Promoted to Standards

**A — `_SCHEMA_VERSION` cache-key spool invalidation pattern** → `CLAUDE.md §Cache Architecture Notes`
Promoted after line 125 ("Spool schema breaking changes"). Pattern: embed `_SCHEMA_VERSION` in query-id hash at write time; bumping the constant on redeploy orphans in-flight parquets by key miss without manual `rm`. Evidence: `downtime_analysis_cache.py::_SCHEMA_VERSION`; `data-shape-contract.md §3.13`; `ci-gates.md §Rollback item 3`.

**B — Multi-parquet atomicity guard** → `CLAUDE.md §Cache Architecture Notes`
Promoted after Lesson A. Pattern: when two interdependent parquets are required for a browser DuckDB-WASM join, validate both atomically and raise `RuntimeError` on partial hit. Evidence: `TestTwoParquetAtomicity::test_base_hit_jobs_miss_raises_loudly`; `contracts/business/business-rules.md §DA-11`.

**C — Parity test atomicity with chunking changes** → *not promoted* (scope too narrow; single-file guidance; no corroborating instance across multiple changes; `test_rowcount_flag_parity.py` is self-documenting).

## Follow-up Work

- Tier 4 OOM stress run (6 GB/no-swap, concurrent 180d queries) — pre-production gate, not pre-merge.
- Nightly Tier 3 184k-row parity run — first run should be monitored manually.
- CI Playwright Tier 2 gate confirmation.
- Post-deploy spool cleanup: `rm tmp/query_spool/downtime_analysis_base_events/*.parquet` + `downtime_analysis_job_bridge/*.parquet`.
- Two-reviewer sign-off (high-risk: qa-reviewer + spec-architect co-sign) before live traffic.
- Enriched-spool deprecation: `/view`, `/equipment-detail`, `/event-detail` endpoints targeted for removal at api 1.17.0.
- Taxonomy label alignment between backend and `useBigCategory.ts` (TBD per roadmap).
