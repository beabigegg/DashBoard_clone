# Archive — msd-type-package-filter

## Change Summary

Added PJ_TYPE (製程類型) and PRODUCTLINENAME (封裝類型) filter dimensions to the MID Section Defect analysis page. A new `GET /api/mid-section-defect/container-filter-options` endpoint returns dynamically-narrowed type/package lists from the detection spool. The frontend FilterBar gained two MultiSelect controls wired to these lists; selection is sent as `pj_types[]`/`packages[]` query params. The backend filters the detection DataFrame before seed resolution (affecting which containers become trace seeds) and also filters the detection spool used for Pareto charts, daily trend, LOT detail, and KPI — ensuring all views reflect the selected filter dimensions.

Two post-implementation bugs were found and fixed: (1) `count_query.sql` was counting `DISTINCT CONTAINERID` instead of the actual combined-CTE row count, causing batch-path detection results to be truncated for date ranges > 10 days; (2) the detection spool passed to `MsdDuckdbRuntime` was the raw (unfiltered) spool, so charts and LOT detail ignored the pj_types/packages filter even after correct seed resolution.

## Final Behavior

- `GET /api/mid-section-defect/container-filter-options?station=…&date_range=…&selected[pj_types][]=…` returns `{ pj_types: [...], packages: [...] }` from detection-spool cache (no Oracle call).
- `POST /api/mid-section-defect/analysis` accepts `pj_types[]`/`packages[]`; filters detection DataFrame before seed resolution and before DuckDB aggregation for all chart/KPI views.
- FilterBar shows "製程類型" and "封裝類型" MultiSelects; selecting a type narrows available packages (cross-filter).
- Batch-path detection row count is accurate: `count_query.sql` counts actual combined-CTE rows (CONTAINERID × LOSSREASONNAME LEFT JOIN pairs), not DISTINCT containers.
- Detection stage spool stored under `trace_query_id` is filtered by pj_types/packages, so `get_detail()` and cached `get_summary()` also see only the filtered rows.

## Final Contracts Updated

- `contracts/api/api-contract.md` → v1.32.0: new `GET /api/mid-section-defect/container-filter-options` endpoint row; analysis endpoint row updated; `MsdContainerFilterOptionsResponse` schema added.
- `contracts/data/data-shape-contract.md` → v1.28.0: §2.13 added (container-filter-options payload shape).
- `contracts/api/api-inventory.md` → v1.2.9: mid_section_defect_routes.py row updated.
- `contracts/CHANGELOG.md`: [api 1.32.0] and [data 1.28.0] entries.
- `contracts/api/openapi.json` + `contracts/openapi.json`: regenerated (186 endpoints).
- `tests/contract/response-samples.json` + `tests/contract/samples/get_mid_section_defect_container_filter_options.json`: new sample.

## Final Tests Added / Updated

Backend (pytest):
- `tests/test_mid_section_defect_service.py`: 7 new tests (pj_type filter reduces rows, package filter, AND semantics, no-filter unchanged, unknown type → empty, empty list → no-filter, null column → no crash)
- `tests/test_mid_section_defect_routes.py`: 7 new tests (pj_types/packages forwarding, container-filter-options endpoint, malformed param handling)
- `tests/e2e/test_mid_section_defect_e2e.py`: 1 new test (cache-not-oracle assertion for filter-options)

Frontend (Vitest / Playwright):
- `frontend/tests/legacy/mid-section-defect-composables.test.js`: 6 new tests (composable URL builder, state shape, cross-filter narrowing)
- `frontend/tests/playwright/mid-section-defect.spec.ts`: 3 new E2E tests (MultiSelect render, cross-filter narrowing)

Total: 32 new tests; 66 tests pass (targeted + changed-area). 160 tests pass after post-implementation fixes.

## Final CI/CD Gates

Required (PR-blocking): unit-and-integration-tests, openapi-sync, contract-and-fast-tests, frontend-unit-tests, e2e-mid-section-defect. All defined in existing workflow files; one step added to `frontend-tests.yml` for the Playwright spec.

## Production Reality Findings

**Bug 1 — batch-path truncation** (`count_query.sql`): The SQL counted `DISTINCT CONTAINERID` from LOTWIPHISTORY (N containers), but `dataset_paged.sql` combined CTE expands to N × avg_loss_reasons rows. `end_row = N` truncated all late-in-range containers when sorted by TRACKINTIMESTAMP ASC — containers appearing only in the latter part of the date range (e.g., PDZ5.6B-AU appearing June 18+ in a June 1–28 query) were silently dropped. Fixed by rewriting `count_query.sql` to count actual combined-CTE rows.

**Bug 2 — unfiltered detection stage** (`trace_job_service` / `msd_duckdb_runtime`): After seed resolution, the detection spool passed to `MsdDuckdbRuntime` was the raw full spool (hash keyed on station + date only, no pj_types). `detection_raw` DuckDB view had no WHERE clause, so Pareto charts, daily trend, and LOT detail showed all-container data regardless of the pj_types/packages filter. Fixed by: (a) adding pj_types/packages WHERE clause to `_register_runtime_views`, (b) passing pj_types/packages through `get_summary_with_detection`, (c) filtering the detection DataFrame with pandas before writing the detection stage spool (so `get_detail()` and subsequent `get_summary()` spool-hit reads are also filtered).

## Lessons Promoted to Standards

- **BQE-08** added to `contracts/business/business-rules.md` (→ v1.33.0): `count_query.sql` must count the same row-unit as the paged SQL combined CTE; counting DISTINCT base entities when the CTE expands to entity×dimension pairs causes silent truncation. Evidence: e76cde22 + count-parity tests.
- **MSD-05** added to `contracts/business/business-rules.md` (→ v1.33.0): container-filter-options endpoint reads only from `container_filter_cache`; no Oracle at request time; cold cache returns empty arrays. Evidence: `test_container_filter_options_uses_cache_not_oracle`.
- **Coarse spool key pattern** added to `docs/architecture/cache-spool-patterns.md` + 1-liner to CLAUDE.md managed region: inject fine-filter WHERE into `_register_runtime_views`; save stage spools under finer keys pre-filtered. Evidence: 4a56ebcd.

## Follow-up Work

- Playwright E2E cross-filter-narrowing test was not executed against a live GunicornHarness in CI (mock-interceptor only). Promote to GunicornHarness-backed test when real-infra CI gate is stabilised.
- `count_query.sql` batch threshold is `BATCH_QUERY_TIME_THRESHOLD_DAYS=10`; the same truncation pattern could affect other batch-mode SQL files — audit `dataset_paged.sql`-pattern files in other modules.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.
