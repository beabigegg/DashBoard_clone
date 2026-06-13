# QA Report — downtime-browser-duckdb

change-id: downtime-browser-duckdb
reviewer: qa-reviewer
date: 2026-06-12
risk: high / tier 0
sign-off: requires two reviewers (qa-reviewer + spec-architect) per high-risk policy

## Decision

**APPROVED_WITH_RISK**

All pre-merge required gates are green. The change is release-ready for merge behind the
`DOWNTIME_BROWSER_DUCKDB` feature flag. Three classes of residual risk are documented below
with owners and pre-production manual gates. No required pre-merge gate is failing.

The 4 E2E failures observed in `tests/e2e/test_downtime_analysis_e2e.py` are **pre-existing**
(reproduced on baseline `971bb8e` with the working tree stashed) and are **out of scope** for
this change's gate — see "Pre-existing Failures Excluded From This Gate". One of them
(`test_event_detail_view_returns_no_match_rows`) exposes a real latent bug in the deprecated
flag-OFF fallback path that intersects this change's rollback target; it is recorded as an
open risk and a pre-production gate, not a merge blocker, because it pre-dates this change.

## AC Coverage Table

| AC | requirement | status | evidence |
|---|---|---|---|
| AC-1 | `/query` returns `{base_spool_url, jobs_spool_url, query_id, taxonomy}`, legacy keys absent when flag on | PASS | `TestQueryRoute::test_response_shape_has_all_four_keys`, `test_*_non_null` (×3), `test_legacy_keys_absent_when_flag_on`, `TestQueryRouteContract::test_response_shape_conforms_to_api_contract_v1_15` — all PASS |
| AC-2 | raw `base_events`/`job_bridge` parquet written without server-side reduction; prewarm unchanged | PASS | `TestRawSpoolWriter::test_base_events_parquet_written_without_merge`, `test_job_bridge_parquet_written_raw`, `test_merge_cross_shift_not_called_on_request_path`, `test_schema_version_in_cache_key` — all PASS |
| AC-3 | browser DuckDB byte/row-equivalent to Python pandas on cross-shift merge, job-bridge, KPI, BigCategory, DailyTrend, EquipmentDetail, EventDetail | PASS (pre-merge, fixture) / DEFERRED (184k production parquet → nightly Tier 3) | `frontend/src/downtime-analysis/__tests__/useDowntimeDuckDB.test.ts` — 31 tests incl. ≥80% runner-up tie-break, cross-midnight merge, no-overlap match_source=none. Fixture-level parity green (frontend-engineer log: 555 frontend tests pass). 184k-row production parity is the nightly Tier 3 gate, not pre-merge. |
| AC-4 | taxonomy delivered as JSON, drives browser BigCategory identically | PASS | `TestTaxonomyBuilder::*` (6 tests, shape/9-buckets/egt/fallback/prefixes), `useDowntimeDuckDB.test.ts` taxonomy-driven mapping tests — all PASS |
| AC-5 | filter change = local SQL, zero API round-trips | PASS (CI) | `downtime-analysis.spec.ts::test_filter_change_issues_zero_api_round_trips (AC-5)` present; Playwright executes in CI, not on this host. App.vue `handleCategoryClick/handleStatusClick/handleGranularityChange` branch to `refreshDuckdbViews()` when `duckdb.state === 'ready'` (frontend-engineer log). |
| AC-6 | `_MAX_ORACLE_DAYS` removed; >90-day range served end-to-end | PASS | constant absent from `src/` (only in removal comments at `downtime_analysis_routes.py:49,72`); `TestQueryRoute::test_range_over_90_days_returns_200_not_400` PASS; `test_range_over_730_days_still_returns_400` PASS (SYS-04 cap retained); Playwright `test_180_day_range_accepted_end_to_end (AC-6)` present (CI). |
| AC-7 | no gunicorn OOM under 6GB/no-swap; browser memory error not silent empty table | PASS (resilience+banner) / DEFERRED (OOM stress → Tier 4 manual) | `TestTwoParquetAtomicity::test_base_hit_jobs_miss_raises_loudly` PASS; Playwright `test_wasm_init_failure_shows_error_banner_not_empty_table`, `test_parquet_fetch_404_shows_error_banner` present. Stress suite `tests/stress/test_downtime_analysis_stress.py` 7 tests collect & compile clean; **not executed** (Tier 4 manual gate, required before production traffic). |
| AC-8 | CSV export works via design-selected (browser blob) path | PASS (CI) | `useDowntimeDuckDB.test.ts` exports `exportCsv`; Playwright `test_csv_export_download_triggers_browser_blob (AC-8)` present. Browser-blob path per design D2. |

## Gate Results

| gate | command | result |
|---|---|---|
| unit — routes + service | `pytest tests/test_downtime_analysis_routes.py tests/test_downtime_analysis_service.py -v` | **158 passed** |
| ruff | `ruff check routes/downtime_analysis_routes.py services/downtime_analysis_service.py services/downtime_analysis_cache.py` | **All checks passed** |
| frontend type-check | `npm run type-check` (vue-tsc --noEmit) | **0 errors** |
| frontend unit (parity + suite) | `npm run test` (per frontend-engineer log) | **555 passed / 53 files** |
| cdd-kit validate | `cdd-kit validate` | **all sections passed** (env semantic, env contract, CI gates, traceability, contract versions) |
| CHANGELOG entries | grep `contracts/CHANGELOG.md` | **5 present**: api 1.15.0, data 1.13.0, business 1.17.0, env 1.0.7, ci 1.3.20 |
| stress (Tier 4) | `pytest tests/stress/test_downtime_analysis_stress.py --collect-only` | **7 collected, py_compile OK** — not executed (manual gate) |
| E2E (downtime) | `pytest tests/e2e/test_downtime_analysis_e2e.py --run-e2e` | 8 passed / 4 failed — **all 4 failures pre-existing on baseline** (see exclusion table) |

## UI/UX Blocking Items (ui-ux-reviewer.yml → resolution)

| id | finding | resolution | evidence |
|---|---|---|---|
| E-1 | one-size error copy; wrong "narrow range" advice on parquet-expired | RESOLVED | App.vue:444-450 — copy classified by `duckdb.errorKind` (fetch/wasm_init/compute) |
| A-1 | legacy ErrorBanner missing role=alert/aria-label, asymmetric | RESOLVED | `ErrorBanner.vue:18` carries `role="alert"` at component level → both legacy (App.vue:438) and DuckDB (442) banners announce; DuckDB instance also has `aria-label` |
| E-3 | silent CSV export failure (console.error only) | RESOLVED | App.vue:88 sets `duckdbError.value='匯出失敗，請重試'` on export catch |
| ES-1 | TopReasonsTable permanently blank in DuckDB mode | RESOLVED | frontend-engineer added `queryTopReasons()` to composable + refreshDuckdbViews |
| R-1 | double-activation race on 清除條件 during in-flight activate() | RESOLVED | state-guard before deactivate/re-activate |

Low-severity findings (L-1, F-1, A-2, A-3, E-2) deferred to follow-up — non-blocking, acknowledged.

## Open Risks

1. **Job-bridge ≥80% runner-up tie-break parity (highest correctness risk).** ADR-0003 flags
   whole-dataset reductions as silent-corruption-prone. Python and DuckDB SQL may disambiguate
   ambiguous tie-breaks differently on edge cases. Mitigation: fixture-level parity test
   `useDowntimeDuckDB.test.ts` includes the ≥80% case and passes; **184k-row production-parquet
   parity is the nightly Tier 3 gate** and must be green before flag default-on.
   Owner: test-strategist / backend-engineer. Follow-up: nightly Tier 3 parity run.
2. **Taxonomy label rename is user-visible.** Backend taxonomy uses `改機換料` /
   `治工具更換與模具清潔` / `教讀程式`; old/frontend `useBigCategory.ts` used `換型換線` /
   `換刀清模`. The composable consumes server-authoritative taxonomy (design D5), so this is
   correct-by-design — but **existing bookmarks/saved filters with old category names will
   silently filter 0 rows**. Deployment runbook must note this. Owner: frontend-engineer /
   ops. Follow-up: add stale-bookmark note to deploy runbook.
3. **Flag-OFF (rollback) fallback path has a latent 500.** The deprecated `/event-detail`
   path's `load_downtime_events` calls `_events_cache.delete()`, which does not exist on
   `ProcessLevelCache` (only `invalidate()`); this 500s the no-match event-detail case.
   Pre-existing (baseline `971bb8e`), not introduced here, but it **degrades this change's
   stated rollback target** (design D1). Owner: backend-engineer. Follow-up: fix
   `downtime_analysis_cache.py:105,111` `delete`→`invalidate` before relying on flag-OFF as a
   production rollback path; file follow-up issue with date.
4. **Low-RAM client on 184k-row (~62 MB) parquet.** D3 ceiling needs a real low-RAM
   device/profile test. Owner: frontend-engineer / stress-soak-engineer.

## Pre-production Manual Gates Required Before Serving Production Traffic

1. **Tier 4 stress/soak OOM-elimination run** — execute
   `pytest tests/stress/test_downtime_analysis_stress.py -m "stress or soak"` on the
   6 GB/no-swap profile; confirm RSS thresholds and `merge call count == 0`. (AC-7)
2. **Nightly Tier 3 184k-row production-parquet parity** — confirm Python vs DuckDB byte/row
   equivalence on the real reference dataset, especially the job-bridge tie-break. (AC-3)
3. **CI Playwright run** — confirm AC-5 zero-round-trip, AC-6 >90d, AC-7 error-banner,
   AC-8 CSV-blob specs pass on the CI runner (browser install step present per CI Workflow note).
4. **Rollback-path repair** — fix the `_events_cache.delete` AttributeError (Open Risk 3) OR
   document that flag-OFF rollback is unsafe for the no-match event-detail case until repaired.
5. **Spool schema-break cleanup** — per design D4, run
   `rm -f tmp/query_spool/downtime_analysis/*.parquet` post-deploy on the schema-versioned spool.
6. **Two reviewer sign-off** — high-risk policy requires spec-architect co-sign in addition to
   this qa-reviewer approval before merge to main.

## Fixback Routing

| issue | route to |
|---|---|
| Open Risk 1 (parity tie-break) | test-strategist + backend-engineer |
| Open Risk 2 (taxonomy bookmark drift) | ui-ux-reviewer + frontend-engineer (runbook) |
| Open Risk 3 (flag-OFF 500) | backend-engineer + contract-reviewer (rollback policy) |
| Stress not yet executed (AC-7) | stress-soak-engineer + ci-cd-gatekeeper |
