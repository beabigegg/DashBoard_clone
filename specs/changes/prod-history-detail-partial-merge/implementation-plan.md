---
change-id: prod-history-detail-partial-merge
schema-version: 0.1.0
last-changed: 2026-05-15
---

# Implementation Plan: prod-history-detail-partial-merge

## Scope

Apply a view-layer 4-tuple aggregation (`lot_id, spec, equipment_id, trackin_time`) over Production-History detail rows so that partial track-outs of one upload session collapse to a single row (`trackin_qty = MAX` = original load qty, `trackout_time = MAX`, `trackout_qty = SUM`, new `partial_count = COUNT(*)`). TRACKINQTY is intentionally NOT a key — see Resolved Decisions §1 for the MES-semantic reason. A strict-guard rule emits raw rows when any non-key column diverges within a group. The same aggregation must apply identically across three paths — DuckDB SQL `compute_detail_page`, pandas fallback `_pandas_detail_page`, and CSV `stream_export` — and `pagination.total_rows` must reflect the post-aggregation count. Frontend DataTable in the production-history app renders a visible badge when `partial_count > 1`.

## Non-goals

- See `change-request.md` §Non-goals: no Oracle/spool parquet schema change, no parquet cleanup, no matrix view / AI query / filter options changes, no detail-row column-semantics shift.
- No new CSS contract change (badge reuses existing design tokens).
- No new CI/CD gate; no e2e specs authored this change.
- No modification of `frontend/src/shared-ui/components/DataTable.vue` unless strictly additive and backward-compatible (prefer keeping the badge inside `frontend/src/production-history/`).

## References

| source | pointer | used for |
|---|---|---|
| `specs/changes/prod-history-detail-partial-merge/change-request.md` | §Constraints, §Non-goals | scope & rule semantics |
| `specs/changes/prod-history-detail-partial-merge/change-classification.md` | AC-1…AC-6 | acceptance criteria |
| `specs/changes/prod-history-detail-partial-merge/test-plan.md` | AC → test mapping; §Notes (TDD order) | tests to write & order |
| `specs/changes/prod-history-detail-partial-merge/ci-gates.md` | Required Gates; §Promotion Policy; §Rollback Policy | verification commands & rollout |
| `contracts/business/business-rules.md` | PH-06, PH-07; Decision Tables rows for partial-trackout | aggregation rule + strict guard |
| `contracts/api/api-contract.md` | §10 compat note 2026-05-15 (lines 284–289) | additive `partial_count` + CSV `PartialCount` + `total_rows` semantics |
| `contracts/data/data-shape-contract.md` | detail-row field table (lines 329–344) | per-field aggregation semantics |
| `specs/archive/2025/prod-history-detail-raw-rows/` | rename-layer note at `production_history_sql_runtime.py:184-205` | confirms no API-key rename needed |

Contracts already updated by `contract-reviewer`. Implementers MUST NOT re-edit contracts (see `specs/changes/prod-history-detail-partial-merge/agent-log/contract-reviewer.yml`).

## File-Level Plan

| path | action | summary | owner |
|---|---|---|---|
| `src/mes_dashboard/services/production_history_sql_runtime.py::compute_detail_page` (~lines 149–225) | modify | Replace the raw-row `SELECT` with an aggregated CTE/subquery: `WITH grp AS (... GROUP BY 4_keys), agg AS (consistent groups, partial_count=COUNT(*)), raw AS (divergent groups, partial_count=1) SELECT * FROM agg UNION ALL SELECT * FROM raw ORDER BY trackin_time, lot_id LIMIT ? OFFSET ?`. Wrap or replace the existing `count_sql` (line 179–181) with a COUNT over the same aggregated set so `total_rows` is post-aggregation. Add a SECOND small COUNT query to compute `<N divergent groups>` for the summary INFO log; emit one log line if `N>0`. Keep the API-key rename layer in the SELECT alias list. | backend-engineer |
| `src/mes_dashboard/services/production_history_sql_runtime.py::_pandas_detail_page` (~lines 228–260) | modify | Pandas emulation of the same SQL aggregation: `groupby(4_keys)` → split groups into consistent vs divergent → emit aggregated row (MAX/SUM/`partial_count=COUNT()`) or raw rows (`partial_count=1`) → concat → paginate. Must produce byte-identical output to the SQL path for the PH-06 parity test. Emit the same summary INFO log line based on divergent-group count. | backend-engineer |
| `src/mes_dashboard/services/production_history_sql_runtime.py::stream_export` (~lines 597–696) + `_pandas_stream_export` | modify | Apply the same SQL aggregation pattern (or pandas equivalent in fallback) before CSV row write loop. Append `("partial_count", "PartialCount")` to `EXPORT_COLUMNS` as the 16th (final) entry. CSV must operate on aggregated rows. Emit the same summary INFO log line based on divergent-group count for the export query. | backend-engineer |
| `src/mes_dashboard/routes/production_history_routes.py` (export route, ~line 432) | no edit expected | Route forwards to `stream_export`; new column flows through transparently. Confirm no header allow-list to update. | backend-engineer |
| `tests/test_production_history_sql_runtime.py` | extend | Add `TestPartialMergeAggregation` class — see test-plan.md AC mapping rows for AC-1/AC-2/AC-4/AC-5/AC-6/PH-06 parity. Use synthetic parquet temp-dir fixture pattern from `tests/test_msd_duckdb_parity.py` (no Oracle/Redis). | backend-engineer |
| `tests/test_production_history_service.py` | extend | Add `TestPandasFallbackAggregation` class — AC-1 pandas, AC-2 pandas ABA, AC-3 strict-guard with `caplog` INFO assertion (group-key payload). | backend-engineer |
| `tests/test_api_contract.py` | extend | Two assertions under existing production-history section: AC-4 (`pagination.total_rows = post-aggregation`) and AC-6 (`partial_count` integer ≥ 1 in row schema). | backend-engineer |
| `frontend/src/production-history/composables/useProductionHistory.ts` (`DetailRow`, ~lines 55–72) | modify | Add `partial_count?: number` field (optional — backward-compat for older backend / rollback per `ci-gates.md` §Rollback step 2). | frontend-engineer |
| `frontend/src/production-history/components/ProductionDetailTable.vue` | modify | In the `#cell` template, when `columnKey === 'lot_id'` and `row.partial_count > 1`, render a small inline badge. Reuse existing Tailwind utility tokens already in production-history; treat missing / undefined / `1` as no-badge. Do NOT modify `frontend/src/shared-ui/components/DataTable.vue`. | frontend-engineer |
| `frontend/tests/legacy/production-history.test.js` | extend | Two Vitest cases for AC-6: badge renders when `partial_count > 1`; badge absent when `partial_count = 1` or undefined. | frontend-engineer |

## Contract Updates

Done by `contract-reviewer`. Implementers do not edit contracts.

- API: `contracts/api/api-contract.md` §10 (lines 284–289) — additive `partial_count`, additive CSV `PartialCount` column, `total_rows` post-aggregation note.
- CSS/UI: n/a (no change).
- Env: n/a.
- Data shape: `contracts/data/data-shape-contract.md` detail-row field table (lines 329–344) updated for 4-tuple semantics + `partial_count`.
- Business logic: `contracts/business/business-rules.md` PH-06, PH-07 + two new rows in Decision Tables.
- CI/CD: n/a (no new gate; existing gates cover new tests — see `ci-gates.md`).

## Test Execution Plan

TDD ordering (cite names from `test-plan.md`):

| step | acceptance | test target | expected signal |
|---|---|---|---|
| 1 | AC-1, AC-2, AC-3 | `tests/test_production_history_service.py::test_pandas_fallback_sum_qty_max_time`, `…_partial_count`, `test_pandas_aba_interleave_not_merged`, `test_strict_guard_fallback_to_raw_rows`, `test_strict_guard_logs_info_with_group_key` | red → green after helper wired into pandas path |
| 2 | AC-1, AC-2, AC-3, AC-4, AC-6 | `tests/test_production_history_sql_runtime.py::test_partial_merge_sum_qty_max_time`, `…_partial_count_equals_group_size`, `…_aba_interleave_not_merged`, `…_duckdb_strict_guard_fallback_to_raw_rows`, `…_pagination_total_rows_is_post_aggregation_count`, `…_detail_row_includes_partial_count_field` | red → green after helper wired into DuckDB path |
| 3 | PH-06 parity, AC-5 | `tests/test_production_history_sql_runtime.py::test_duckdb_pandas_parity_aggregation_output`, `…_csv_rows_match_api_rows_aggregated`, `…_csv_partial_count_matches_api` | green; byte-for-byte parity |
| 4 | AC-4, AC-6 (contract) | `tests/test_api_contract.py::test_production_history_detail_pagination_total_rows_post_aggregation`, `…_detail_row_schema_has_partial_count_integer` | green |
| 5 | AC-6 (frontend) | `frontend/tests/legacy/production-history.test.js::test partial_count badge renders when value gt 1`, `…absent when value equals 1` | green after badge added |
| 6 | gate sweep | `conda run -n mes-dashboard pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x`; `cd frontend && npm run test`; `npm run css:check`; `cdd-kit validate` | all required gates per `ci-gates.md` |

## Constraints

- Logger level for strict-guard divergence MUST be `INFO`, not `WARNING` (PH-07; `change-classification.md` §Clarifications #3). **Summary form**: ONE log line per request when `N>0` divergent groups, no per-group enumeration.
- `pagination.total_rows` MUST equal post-aggregation row count — never raw spool row count. Wrap or replace the existing `count_sql` accordingly.
- SQL and pandas paths MUST produce identical output for the PH-06 parity test (same row count, same per-row column values, same partial_count). Pandas path is fallback-only (when `_SQL_VIEW_ENABLED=False`); SQL is the primary.
- CSV `PartialCount` is column 16 (final), AFTER `TrackOutQty`. Do not reorder existing columns.
- No parquet cleanup on rollback; spool schema unchanged (`ci-gates.md` §Rollback).
- Frontend defensive coding: `partial_count` optional on `DetailRow`; missing / `undefined` / `1` → no badge. Supports partial-deploy and rollback scenarios.
- Shared component additive rule: `DataTable.vue` used by 9 apps (CLAUDE.md §Shared UI Component Notes). Keep badge in `production-history/components/`. If a slot must be added to shared DataTable, it MUST be optional and default to existing behavior — but prefer NOT touching it.
- Use Conda env `mes-dashboard` for all Python work.
- Do not author new tests in `tests/integration`, `tests/stress`, `tests/e2e`, or `tests/manual` (test-plan.md §Out of Scope).
- Badge label format locked: `×<N> 合併` (numeric + 合併 label). Project has no i18n requirement (confirmed by user 2026-05-15); no i18n file updates needed.

## Resolved Decisions (locked 2026-05-15 by user)

1. **Backend aggregation site → SQL-only (option 1a), 4-tuple key.** Pure DuckDB SQL with `GROUP BY` on the 4-tuple (`CONTAINERNAME, SPECNAME, EQUIPMENTID, TRACKINTIMESTAMP`) + `HAVING COUNT(DISTINCT col)=1` for every non-key column to gate the aggregated branch + `UNION ALL` with a raw-rows branch (filtered to divergent groups) for the strict-guard fallback. `partial_count = COUNT(*)` in the aggregated branch and `1` in the raw branch. Aggregated row uses `MAX(TRACKINQTY)` (= original load qty) and `SUM(TRACKOUTQTY)`. **Why 4-tuple not 5-tuple (initial spec was 5-tuple including TRACKINQTY)**: this MES records `TRACKINQTY` as the qty REMAINING at the start of each partial trackout (decreasing across partials of one upload), NOT the original load. Keeping TRACKINQTY in the key would mean partial-trackout rows NEVER merge — defeating the change. A/B-lot interleaving is still preserved by `TRACKINTIMESTAMP` (A's re-upload has a different timestamp). Evidence: lot `GA26041607-A00-005` on equipment `GWBA-0146`, TrackIn `2026-04-30 00:09:29`, two partial trackouts with TRACKINQTY `99424` and `26624` (= 99424 − 72800). **Reason for SQL-only over helper:** avoid pulling raw rows into Python pandas — DuckDB streams the aggregation over parquet with minimal RAM. The `production_history_aggregation.py` helper module is therefore NOT created. The same SQL pattern is applied to all three paths (DuckDB main, pandas fallback, CSV stream); the pandas fallback uses pandas `groupby` to emulate the same logic (this fallback only runs when `_SQL_VIEW_ENABLED=False`, kept for resilience parity).
2. **Frontend badge → numeric + text label.** Render `×<N> 合併` (e.g., `×3 合併`) where N is `row.partial_count`. Project has no i18n requirement (confirmed by user), so the Chinese label is safe. Place the badge inline next to `lot_id` in `ProductionDetailTable.vue`. No update to shared DataTable or design tokens.
3. **Strict-guard INFO log → summary per request.** Emit at most ONE INFO log line per detail-page / CSV request, of the form:
   `INFO partial-trackout strict-guard: <N> divergent groups fell back to raw rows (query_id=<id>, total_groups=<M>)`
   where `<N>` is the count of 4-tuple groups that hit the strict-guard fallback and `<M>` is the total number of 4-tuple groups in the query result. Suppress when `N == 0`. Implementation: a single small COUNT query (`SELECT COUNT(*) FROM (... GROUP BY 4-keys HAVING COUNT(DISTINCT col)>1 OR ...)`) executed alongside the main page/export query; do NOT enumerate group keys to avoid log flooding. Per-group keys can be added later if operators need finer debugging.

## Execution Order

1. **Backend.**
   1. Write failing unit tests for AC-1/AC-2/AC-3 in `tests/test_production_history_service.py` (pandas fallback path).
   2. Write failing unit tests for AC-1/AC-2/AC-3/AC-4/AC-6 in `tests/test_production_history_sql_runtime.py` (DuckDB primary path).
   3. Implement the aggregated SQL pattern (`GROUP BY` + `HAVING COUNT(DISTINCT)=1` per non-key + `UNION ALL` raw fallback + `partial_count`) inside `compute_detail_page`. Build the second small COUNT query for summary INFO log.
   4. Implement pandas equivalent in `_pandas_detail_page` (same row output, same INFO log).
   5. Implement same SQL/pandas aggregation in `stream_export` + `_pandas_stream_export`; append `PartialCount` to `EXPORT_COLUMNS`.
   6. Add contract assertions (AC-4, AC-6) in `tests/test_api_contract.py`.
   7. Add parity + CSV-parity tests; make all green.
2. **Frontend.**
   1. Write Vitest cases for badge rendering (AC-6).
   2. Add `partial_count?: number` to `DetailRow` interface.
   3. Render badge in `ProductionDetailTable.vue` next to `lot_id`.
   4. Run `npm run test`, `npm run css:check`, `npm run type-check`.
3. **Gate sweep locally.** `cdd-kit validate` + the PR-required gates list from `ci-gates.md`.
4. **Reviewers:** `ui-ux-reviewer` (badge placement / accessibility), `visual-reviewer` (informational screenshot diff), `qa-reviewer` (final verdict).

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.

## Known Risks

- **Parity slippage** between SQL and pandas paths if approach (1a) is chosen. Mitigation: PH-06 parity test (`test_duckdb_pandas_parity_aggregation_output`) is mandatory; if it fails repeatedly, switch to (1b).
- **Memory pressure** on large date-range queries when the helper materialises filtered rows in pandas before pagination. Existing `SPOOL-03` 503 guard remains; no new guard added. Stress is out of scope (Tier 2). If `compute_detail_page` regresses measurably on the largest known query, reconsider approach (1a) for that path while keeping (1b) for `stream_export`.
- **CSV consumers** parsing by column position will see a new trailing column — documented as additive in `api-contract.md` §10 (2026-05-15 note).
- **Partial deploy** (backend before frontend) shows no badge but is otherwise correct — defensive frontend handling covers it.
