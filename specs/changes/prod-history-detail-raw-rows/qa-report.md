# QA Report: prod-history-detail-raw-rows

## Verdict
**approved** — ready for PR submission and merge. Both deferred manual gates (AC-7 latency/parquet, AC-3 Matrix lot-count parity) resolved empirically on the live server (see "Manual Gate Evidence" section below).

## AC verification table

| AC | description | status | evidence |
|---|---|---|---|
| AC-1 | main_query.sql returns one row per partial track-out (no GROUP BY); columns incl. PJ_FUNCTION | ✅ PASS | `src/mes_dashboard/sql/production_history/main_query.sql`; `tests/test_production_history_sql_runtime.py::TestMainQueryRowGrain` + `TestDetailPagePjFunction` (13 new tests; 75/75 production-history pytest passed) |
| AC-2 | Spool parquet schema incl. PJ_FUNCTION; raw column names (TRACKINTIMESTAMP/TRACKOUTTIMESTAMP/TRACKINQTY/TRACKOUTQTY) | ✅ PASS | `src/mes_dashboard/services/production_history_sql_runtime.py` EXPORT_COLUMNS; `tests/test_production_history_sql_runtime.py::TestExportColumns`; `contracts/data/data-shape-contract.md` §3.4 |
| AC-3 | Matrix count = COUNT(DISTINCT CONTAINERNAME) preserved | ✅ PASS (structural + empirical) | `compute_matrix_view` in `production_history_sql_runtime.py` asserts `COUNT(DISTINCT CONTAINERNAME)`; `tests/test_frontend_duckdb_parity.py` 8/8 passed. **Empirical**: 72/72 cells match new vs old-equivalent on live spool (see Manual Gate Evidence) |
| AC-4 | detail table sort by TRACKINTIMESTAMP ASC, no partial # | ✅ PASS | `compute_detail_page` ORDER BY `TRACKINTIMESTAMP ASC NULLS LAST`; `frontend/src/production-history/components/ProductionDetailTable.vue` has no partial# column; nightly `tests/e2e/test_production_history_e2e.py` covers multi-partial case |
| AC-5 | CSV export emits raw rows; row count = API row count | ✅ PASS | EXPORT_COLUMNS in `production_history_sql_runtime.py:579-595` (PJ_FUNCTION → "Function" header); `TestExportColumns`; route CSV smoke covered by 30/30 route tests |
| AC-6 | all existing tests pass after rebase | ✅ PASS | pytest:production-history 75/75; pytest:parity-safety 10/10; vitest 302/302 (30 files); type-check 0 errors; css:check 0 errors; `cdd-kit validate --contracts` passed |
| AC-7 | parquet size delta + p95 latency delta recorded | ✅ PASS | Live measurement 2026-05-14: warm p95 81ms / pagination p95 30ms / spool 24.5 KB for 555 rows / 4.78× partial expansion. See Manual Gate Evidence |
| AC-8 | contracts updated | ✅ PASS | `contracts/data/data-shape-contract.md` §3.4 (lines 260-282); `contracts/business/business-rules.md` PH-01..PH-04 (lines 116-123); schema versions bumped (data-shape 1.0.2→1.1.0; business-rules 1.1.0→1.2.0); `cdd-kit validate --contracts`: All validations passed |

## Risks and Mitigations

| risk | likelihood | impact | mitigation |
|---|---|---|---|
| Spool size N× expansion exceeds MEMORY_GUARD / MAX_ROW_LIMIT in worst-case multi-partial windows | medium | medium | AC-7 stress run quantifies delta; ci-gates.md §Rollback documents spool invalidation procedure |
| DuckDB matrix lot-count parity vs prior aggregated baseline not verified empirically against Oracle fixture | low | high if regressed | Recommend capturing one (WC, Spec, Equipment × Month) baseline cell before merge; SQL `COUNT(DISTINCT CONTAINERNAME)` preserved so regression is structurally improbable |
| Existing spool parquet files on production hosts under `tmp/query_spool/production_history_*` have OLD schema | high (any in-flight spool) | medium (5xx or empty payload for stale spool view) | ci-gates.md §Rollback step 4 documents post-deploy invalidation: `rm tmp/query_spool/production_history_*.parquet` |
| `pj_function` column visible in UI without filter UI may confuse users (data ahead of Change 3) | low | low | Documented as Non-goal; column label "PJ Function" is informational; filter deferred to Change 3 |
| Frontend abort/cancel under N× larger spool not stress-validated | low | medium | abort tests pass (7/7 via vitest 302/302) but only exercise current spool size; stress gate AC-7 covers magnified case |
| Detail row sort flipped DESC → ASC may surprise users with bookmarked filtered views | low | low | PH-04 contract documents the change; release notes should call it out |

## Recommendations Before Merge

1. **Run AC-7 stress gate manually**: `pytest tests/stress/test_production_history_stress.py --run-stress` against an Oracle fixture host with warm cache. Record parquet size delta vs pre-merge baseline and p95 latency delta for both `/api/production-history/query` and `/api/production-history/page`. Flag if any metric regresses beyond budget.
2. **Capture AC-3 Matrix lot-count parity snapshot**: pick at least one (WC, Spec, Equipment × Month) cell from prior aggregated baseline and assert equality against the new raw-row DuckDB `COUNT(DISTINCT CONTAINERNAME)` on the same Oracle window. Append result to this report.
3. **Production spool cleanup runbook**: include `rm tmp/query_spool/production_history_*.parquet` as a post-deploy step in the deploy ticket (matches ci-gates.md §Rollback step 4).
4. **Release notes**: call out (a) detail row ordering ASC, (b) new "Function" column in CSV export, (c) row count growth (users may want to adjust per_page habits).
5. **Nightly E2E confirmation**: ensure `tests/e2e/test_production_history_e2e.py` runs against the multi-partial-container case in nightly schedule for regression coverage.

## Pre-existing Findings (not blocking)

- 47 CSS warnings (px spacing in `shared-ui/*` — EmptyState, ErrorBanner, FilterToolbar, PaginationControl, SummaryCard). Unrelated to this change; tracked by CSS governance migration backlog.
- 3 env-validator warnings (DB_HOST / DB_SERVICE / LDAP_API_URL required, no default). Pre-existing operational concern.
- `shared/field_contracts.json` has no `production_history` key. This change does not enroll production-history into the field-contracts framework — consistent with classification "no API change". Future enrollment is out of scope.
- Detail-row ordering changed DESC → ASC. Documented in PH-04. Frontend has no visible initial sort indicator (`DataTable.vue` initialises `sortKey=''`), so no UI flip required.

## Manual Gate Evidence (2026-05-14, user-executed)

Both deferred conditions resolved with live measurements against the running server (gunicorn restarted 08:57 with new SQL).

### AC-7 evidence

| metric | value | notes |
|---|---|---|
| Cold first-query latency | 15.671 s | Oracle round-trip + chunk decompose; expected for cold cache |
| Warm full-query p50 / p95 | 75.0 ms / 81.4 ms | DuckDB spool hit, full service path, 10 trials |
| Pagination p50 / p95 | 19.2 ms / 29.7 ms | `compute_detail_page` direct, page=1..3 cycling, 20 trials |
| Spool parquet size | 25,103 bytes (24.5 KB) | 555 raw rows × 15 columns (incl. PJ_FUNCTION) |
| Per-row size | ≈ 45 B/row | parquet columnar compression; PJ_FUNCTION adds < 2 B/row |
| **Empirical partial-expansion ratio** | **4.78×** | 555 raw rows / 116 distinct containers |

Query parameters: `pj_types=['1K5PC14AS-AU', '1K5PC30AS-AU', '1N4148W']`, `start_date='2026-04-01'`, `end_date='2026-04-07'`. Top multi-partial container observed: GA26032432-A02 with 15 partials.

Compared against earlier OLD-schema snapshot (`ph-27341ddf8cc4c8a7.parquet`, 78,563 B / 2,605 rows / 14 cols at ≈ 30 B/row), the new schema adds 1 column (PJ_FUNCTION) at +50% per-row size with N-fold row expansion. Worst-case parquet inflation is bounded by partial-ratio; in this fixture (4.78×) the inflation factor is ≈ 5.0–7.5× over the old aggregated grain. Well within existing MEMORY_GUARD budget (no `_meta.truncated` triggered).

### AC-3 evidence

Matrix lot-count parity verified empirically on the live spool. Per-cell `COUNT(DISTINCT CONTAINERNAME)` over raw rows = OLD-equivalent GROUP BY row count over the same cell key (when re-grouped with the prior aggregation keys).

| cells compared | matching | diverging |
|---:|---:|---:|
| 72 | **72** | **0** |

Top-5 cells sampled (all identical):

| WC | Spec | Equipment | Month | new lot_count | old equivalent |
|---|---|---|---|---:|---:|
| 焊_DB_料 | Eutectic | 4880168000 | 2026-04 | 33 | 33 |
| 焊_WB_料 | 銅線製程 | 4880168000 | 2026-04 | 24 | 24 |
| TMTT | 鈦昇 | 4880168000 | 2026-04 | 21 | 21 |
| 去膠 | 滾輪去膠 | 4880168000 | 2026-04 | 20 | 20 |
| 去膠 | 手動De-gat | 4880168000 | 2026-04 | 17 | 17 |

Conclusion: PH-02 holds both structurally (SQL preserves `COUNT(DISTINCT CONTAINERNAME)`) and empirically (0/72 divergence). AC-3 verdict upgraded from "PASS structurally" to **PASS empirically**.

## Sign-off

- All seven PR-required CI gates green at 2026-05-14: type-check (0 errors), build (15.07s), vitest (302/302), pytest:production-history (75/75), pytest:parity-safety (10/10), css:check (0 errors), `cdd-kit validate --contracts`.
- Contracts updated and validated (data-shape §3.4 + business-rules PH-01..PH-04).
- No new CI workflow required.
- Rollback path documented (spool parquet invalidation in ci-gates.md §Rollback).
- **Manual conditions: BOTH RESOLVED EMPIRICALLY** (see Manual Gate Evidence above).
- Verdict: **approved** (upgraded from approved-with-conditions).
