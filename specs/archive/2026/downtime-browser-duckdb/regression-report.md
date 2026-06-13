# Regression Report — downtime-browser-duckdb

change-id: downtime-browser-duckdb
reviewer: qa-reviewer
date: 2026-06-12

## 1. Regression Scope

This change replaces the **entire server-side compute path** of the released
downtime-analysis page when `DOWNTIME_BROWSER_DUCKDB=true`:

| existing behavior (flag OFF / prior) | replaced by (flag ON / this change) |
|---|---|
| `POST /api/downtime-analysis/query` returns server-pre-aggregated `{query_id, summary, daily_trend, big_category, top_reasons}` | returns `{base_spool_url, jobs_spool_url, query_id, taxonomy}`; aggregation moved to browser DuckDB-WASM |
| `_merge_cross_shift_events` runs on the request path (server pandas) | runs as browser DuckDB SQL on raw `base_events.parquet` |
| `_bridge_jobid` job-overlap bridge runs server-side | runs as browser DuckDB SQL on raw `job_bridge.parquet` |
| `_map_big_category` applied server-side, baked into response | delivered as taxonomy JSON, applied browser-side (design D5) |
| filter change → new `/view` `/equipment-detail` `/event-detail` API round-trip | filter change → local browser SQL, zero round-trips (AC-5) |
| `_MAX_ORACLE_DAYS` (90-day) guard rejects wide ranges with 400 | removed; >90d accepted end-to-end, 730-day SYS-04 cap retained |
| CSV export via server-side `export_*_csv` streamers | browser-blob export from DuckDB result (design D2) |

Compute-relocation of correctness-critical reductions (`_merge_cross_shift_events`,
`_bridge_jobid`) is the principal regression surface. ADR-0003 explicitly warns these
whole-dataset reductions are silent-corruption-prone if split. The raw spool write uses a
single whole-dataset BQE chunk (design D8) so no logical event is split at a chunk seam.

## 2. Coverage Table (existing behavior → test now guarding it)

| prior behavior | new guarding test | result |
|---|---|---|
| cross-shift merge correctness | `useDowntimeDuckDB.test.ts` cross-midnight merge / gap>60s / status-mismatch / event-count parity; Python reference retained in `tests/test_downtime_analysis_service.py::TestCrossShiftMerge` | PASS |
| job-overlap bridge incl. ≥80% runner-up tie-break | `useDowntimeDuckDB.test.ts` Path A / Path B / ambiguous tie-break / null-JOBID / match_source=none; `TestJobidBridge` (Python reference) | PASS |
| big-category mapping (9 buckets) | `TestTaxonomyBuilder::*` + `useDowntimeDuckDB.test.ts` taxonomy-driven mapping | PASS |
| KPI summary / daily trend / equipment + event detail | `useDowntimeDuckDB.test.ts` kpi/daily-trend/equipment-detail/event-detail parity tests | PASS |
| `/query` response shape | `TestQueryRouteContract::test_response_shape_conforms_to_api_contract_v1_15`; `TestQueryRoute` 4-key + legacy-absent | PASS |
| per-kwarg filter forwarding (start/end/status/resource/big_category) | `TestFilterKwargsForwarding::*`, `TestQueryRoute::test_*_forwarded_flag_on` | PASS |
| raw spool write w/o server reduction | `TestRawSpoolWriter::*`, `TestPrewarmFeedRawWriter` (mapped) | PASS |
| zero-round-trip filtering (new) | Playwright `test_filter_change_issues_zero_api_round_trips (AC-5)` (CI) | present |
| CSV export equivalence | `useDowntimeDuckDB.test.ts` exportCsv; Playwright CSV-blob (CI) | present |
| 184k-row production parity | nightly Tier 3 gate | DEFERRED (not pre-merge) |

## 3. Removed Capability: 90-day Oracle fallback limit

`_MAX_ORACLE_DAYS` (90) and its check in `_validate_dates()` are **intentionally removed**
(AC-6). This is **not a regression** — it was a deployed band-aid that capped query width to
avoid OOM-killing gunicorn workers on the server-side pandas reduction. The browser-DuckDB
architecture eliminates that server-side reduction (AC-2/AC-7), so the cap is no longer needed.
The 730-day SYS-04 hard cap is retained (`test_range_over_730_days_still_returns_400` PASS).

**Conditional regression caveat:** the removal is only safe while the browser path is active.
If the system is rolled back to the flag-OFF server path under the 6 GB/no-swap profile, wide
ranges re-introduce OOM risk. This is documented in `ci-gates.md §Rollback Policy` and must be
honored: re-introduce the limit on rollback, or accept the OOM risk knowingly.

## 4. Deprecated Endpoints — flag-OFF path status

`GET /api/downtime-analysis/view`, `/equipment-detail`, `/event-detail` are deprecated in place
(design D1, removal target api 1.17.0) and kept alive as the flag-OFF rollback target.

| endpoint | flag-OFF status | evidence |
|---|---|---|
| `/view` | alive (route + `apply_view` retained) | `TestApplyViewFilter::*` (8 tests) PASS |
| `/equipment-detail` | alive | `apply_view` equipment-detail filter tests PASS |
| `/event-detail` | alive but **latent 500 on no-match case** | see §5 — pre-existing `_events_cache.delete` bug |

The flag-OFF response shape (`{query_id, summary, daily_trend, big_category, top_reasons}`) is
restored with no redeploy (`TestQueryRoute::test_feature_flag_off_returns_legacy_shape` PASS).

## 5. Residual Risk: flag-OFF OOM + latent 500

1. **OOM risk on flag-OFF wide ranges** — documented in rollback policy (§3). The server-side
   pandas reduction path still exists behind the flag; rolling back without re-introducing the
   90-day cap re-exposes the OOM that motivated this change. Owner: ci-cd-gatekeeper / ops.

2. **Latent 500 in flag-OFF `/event-detail` no-match path** — `load_downtime_events`
   (`downtime_analysis_cache.py:105,111`) calls `_events_cache.delete()`, but `ProcessLevelCache`
   exposes only `invalidate()`. The no-match event-detail case 500s. **Pre-existing** (reproduced
   on baseline `971bb8e` with this change's working tree stashed — identical error at the same
   call site, blame commit `afe27233` 2026-05-29), so it is NOT a regression introduced by this
   change. However, because flag-OFF is this change's declared rollback target (design D1), the
   rollback path is partially broken until this is fixed. Recommend `delete`→`invalidate` repair
   before relying on flag-OFF rollback in production. Owner: backend-engineer. Follow-up: file
   issue with date; route to backend-engineer + contract-reviewer (rollback policy).

3. **Test-harness drift (not a product regression)** — `TestSummaryEndpointIntegration` and
   `TestEventDetailMatchSourceNoneRowsPresent::test_no_match_events_included_in_summary` patch
   `load_downtime_events` at the service module (`mes_dashboard.services.downtime_analysis_service`)
   instead of the definition site (`...downtime_analysis_cache`) per CLAUDE.md, so the patch never
   applies. Pre-existing on baseline. Recommend repatching to the cache site. Owner: test-strategist.
