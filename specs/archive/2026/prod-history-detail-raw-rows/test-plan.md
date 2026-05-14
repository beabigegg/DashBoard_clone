---
change-id: prod-history-detail-raw-rows
schema-version: 0.1.0
last-changed: 2026-05-14
risk: medium
tier: 2
---

# Test Plan: prod-history-detail-raw-rows

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 (no GROUP BY; raw cols + PJ_FUNCTION) | unit | `tests/test_production_history_sql_runtime.py` (`compute_detail_page` row-grain + projection assertions; `_build_filter_where` audit) | 2 |
| AC-2 (spool parquet schema incl. PJ_FUNCTION; raw col names) | contract | `tests/test_production_history_service.py` (spool schema introspection) + `tests/test_production_history_sql_runtime.py::stream_export` | 2 |
| AC-3 (Matrix `count` = COUNT(DISTINCT CONTAINERNAME) parity vs aggregated baseline) | integration + parity | `tests/test_frontend_duckdb_parity.py` (production-history Matrix case) + `tests/integration/` Oracle-fixture run | 2 |
| AC-4 (detail UI: one row per partial, ordered by TRACKINTIMESTAMP, no "partial #" col) | e2e + unit | `tests/e2e/test_production_history_e2e.py` (multi-partial container) + `frontend/tests/legacy/production-history.test.js` | 2 |
| AC-5 (CSV export = raw per-partial rows; row count = API row count) | unit + integration | `tests/test_production_history_sql_runtime.py::stream_export` + `tests/test_production_history_routes.py` (CSV endpoint smoke) | 2 |
| AC-6 (no regression: existing parity/safety/abort/contract pass after fixture rebase) | regression suite | full pytest + `frontend/tests/abort/production-history-abort.test.js` + `frontend/tests/validation/useProductionHistory.validation.test.js` | 2 |
| AC-7 (qa-report: spool size delta, p95 latency delta, DuckDB budget) | stress | `tests/stress/test_production_history_stress.py` (one-shot manual gate) | 2 |
| AC-8 (data-shape §3.4 + business-rules PH-01..PH-04 reflect new grain) | contract | `cdd-kit validate --contracts` + `tests/test_field_contracts.py` | 2 |

Data-boundary (PH-04 + Matrix correctness): cross-month partial — added to `tests/test_production_history_sql_runtime.py` (`test_matrix_attributes_partial_by_trackin_timestamp`) and to e2e via fixture seed.

## Test Families Required

unit (sql_runtime, service, job_service, routes — row-grain + PJ_FUNCTION carry-through), contract (data-shape §3.4 + business-rules PH-01..PH-04 + field-contracts), integration (Oracle-fixture row-count = LOTWIPHISTORY count; Matrix lot-count parity vs prior aggregated baseline), e2e (multi-partial container renders multi-row, ordered by TRACKINTIMESTAMP), data-boundary (cross-month partial attribution by TRACKINTIMESTAMP, no double-count), resilience (production-history-abort under N× larger spool), parity (`test_frontend_compute_parity.py` + `test_frontend_duckdb_parity.py` rebased), stress (one-shot manual: parquet size + p95 latency delta).

Not applicable: monkey/fuzz (mechanical SQL row-grain change), soak (no long-running state), visual (Non-goals forbid component-structure change).

## Audit Checklist (before implementation completes)

1. **BLOCKING (backend-engineer)**: PJ_FUNCTION column source verification on `DWH.DW_MES_CONTAINER` — DESCRIBE table or reuse the WIP filter-options service path (already extracts PJ_FUNCTION per data-shape §2.5). If absent, file Context Expansion Request before adding to projection.
2. **BLOCKING (frontend-engineer)**: audit `frontend/src/production-history/` and `frontend/src/core/field-contracts.ts` / `endpoint-schemas.ts` for hardcoded `TRACKIN_TS` / `TRACKOUT_TS` / `TRACKIN_QTY` / `TRACKOUT_QTY` aliases — rename to raw `TRACKINTIMESTAMP` / `TRACKOUTTIMESTAMP` / `TRACKINQTY` / `TRACKOUTQTY`.
3. Regenerate parity fixtures: `tests/fixtures/frontend_compute_parity.json` + any production-history spool snapshots referenced from `test_frontend_duckdb_parity.py`. Capture an aggregated-baseline Matrix snapshot first so AC-3 has a reference.
4. Re-run `tests/stress/test_production_history_stress.py` with the new spool size; record parquet size delta + p95 latency delta in qa-report.md. Flag if MEMORY_GUARD / MAX_ROW_LIMIT need adjustment (per contract-reviewer note).
5. Confirm Matrix `COUNT(DISTINCT CONTAINERNAME)` parity against the prior aggregated baseline for ≥1 (WC, Spec, Equipment × Month) cell on the integration fixture.

## Out of Scope

- Visual / UI-UX review (Non-goals: no component-structure change).
- Monkey / fuzz tests (not applicable for a SQL row-grain change).
- Soak tests (not applicable).
- Filter UI additions — PJ_FUNCTION is staged in spool only; surfacing as a filter is deferred to Change 3 `prod-history-first-tier-cache-filters`.

## Notes

- Stress test runs as a **one-shot manual gate during qa-reviewer phase**, not a PR gate.
- Data-boundary case: same container with partial-A in month N and partial-B in month N+1 must be attributed by `TRACKINTIMESTAMP`; Matrix must not double-count the lot.
- **Parity fixture rebase is a prerequisite step**: must land before backend-engineer's SQL rewrite can pass parity tests. Flag this dependency in `tasks.yml` (rebase task before backend SQL task).
- API response envelope unchanged — `tests/test_api_contract.py` re-run only as smoke, no schema bump.
