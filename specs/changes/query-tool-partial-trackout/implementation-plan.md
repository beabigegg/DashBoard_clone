---
change-id: query-tool-partial-trackout
schema-version: 0.1.0
last-changed: 2026-05-15
---

# Implementation Plan: query-tool-partial-trackout

## Objective

Replace `ROW_NUMBER()` dedup with a 4-tuple / 3-tuple partial-trackout aggregation + strict guard across the three query-tool Oracle SQL paths, mirroring the reference implementation in `production_history_sql_runtime.py` (commit 49f5e48). Aggregation lives in Python; Oracle SQL retains only the raw row fetch. Post-aggregation rows include an additive `partial_count` column. API JSON field names are unchanged.

## Execution Scope

### In Scope
- Strip the `ROW_NUMBER()` dedup layer from `lot_history.sql`, `equipment_lots.sql`, and the inner `raw_lots → deduped_lots` CTE of `adjacent_lots.sql`. Oracle returns one row per LOTWIPHISTORY partial.
- Add a shared aggregation helper in `query_tool_sql_runtime.py` (pandas + DuckDB-in-process style, mirroring `_pandas_aggregate_partial_trackouts` in `production_history_sql_runtime.py`). Helper computes `TRACKINQTY=MAX`, `TRACKOUTQTY=SUM`, `TRACKOUTTIMESTAMP=MAX`, `partial_count=COUNT(*)` and applies the QT-06 strict guard.
- Call the helper from `query_tool_service.get_lot_history` / `get_lot_history_batch` / `get_equipment_lots` / `get_adjacent_lots` immediately after the Oracle fetch DataFrame is materialised, before pagination/spool-store.
- Preserve the outer `ranked_lots` `ROW_NUMBER() ... AS rn` (and the `RELATIVE_POSITION` derivation) in `adjacent_lots.sql`. Aggregation happens INSIDE the inner CTE so the outer relative-position ranks neighbors of aggregated groups.
- Extend test-plan.md test cases via new file `tests/test_query_tool_partial_trackout.py` and one new case in `tests/test_query_tool_sql_runtime.py` (see ci-gates.md §Required Gates).

### Out of Scope
- Other query-tool SQL files in `src/mes_dashboard/sql/query_tool/` (`lot_materials.sql`, `lot_rejects.sql`, `lot_holds.sql`, `lot_jobs*.sql`, `equipment_jobs.sql`, `equipment_materials.sql`, `equipment_recent_jobs.sql`, `lot_splits.sql`). They do not use the partial-trackout ROW_NUMBER pattern. Confirmed via `change-classification §Inferred Acceptance Criteria` and `test-plan.md §Out of Scope`.
- Production-history paths (already implemented in commit 49f5e48).
- Frontend display of `partial_count`. Field is exposed; consumers ignoring unknown columns are unaffected (QT-05).
- Oracle `integration_real` nightly gate. `test-plan.md §Out of Scope` confirms Oracle real-infra is not pre-merge.
- New CI workflows or path filters. `ci-gates.md §CI/CD Workflow` confirms the existing `backend-tests.yml` path filter `src/mes_dashboard/sql/**` already covers all three SQL files.
- Spool parquet schema cleanup. `ci-gates.md §Rollback Policy` confirms query-tool is on-demand Oracle with no persisted parquet sentinel files; the in-memory aggregation produces post-aggregated rows before the (in-memory) spool is written, so the `partial_count` column lands naturally inside any subsequent spool dataframe with no schema migration.

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | SQL — `lot_history.sql` | Remove the `ROW_NUMBER() OVER (PARTITION BY h.CONTAINERID, h.EQUIPMENTID, h.SPECNAME, h.TRACKINTIMESTAMP ORDER BY h.TRACKOUTTIMESTAMP DESC NULLS LAST) AS rn` window and the outer `WHERE rn = 1`. Project raw columns directly. Keep `ORDER BY TRACKINTIMESTAMP`. Update header comment to point at QT-05/QT-06. | backend-engineer |
| IP-2 | SQL — `equipment_lots.sql` | Same removal as IP-1, applied to the `ranked_lots` CTE. Keep `ORDER BY EQUIPMENTNAME, TRACKINTIMESTAMP`. Update header comment. | backend-engineer |
| IP-3 | SQL — `adjacent_lots.sql` | Remove the `ROW_NUMBER() ... AS dedup_rn` window inside `raw_lots` and remove the `deduped_lots AS (SELECT * FROM raw_lots WHERE dedup_rn = 1)` CTE. Replace with a `raw_lots` CTE that simply projects the raw columns; the outer `ranked_lots /*+ MATERIALIZE */` CTE with `ROW_NUMBER() OVER (PARTITION BY d.EQUIPMENTID ORDER BY d.TRACKINTIMESTAMP) AS rn` and all downstream CTEs (`target_lot`, `first_diff_before`, `first_diff_after`, final SELECT, `RELATIVE_POSITION` derivation) MUST remain byte-identical. Aggregation will be applied in Python BEFORE `RELATIVE_POSITION` is consumed — see IP-6. | backend-engineer |
| IP-4 | Python — `query_tool_sql_runtime.py` | Add module-level constants `_PARTIAL_KEY_COLS_4` (= `[CONTAINERID, EQUIPMENTID, SPECNAME, TRACKINTIMESTAMP]`), `_PARTIAL_KEY_COLS_3` (= `[CONTAINERID, EQUIPMENTID, TRACKINTIMESTAMP]`), and `_PARTIAL_NONKEY_COLS_LOT_HISTORY` / `_PARTIAL_NONKEY_COLS_EQUIPMENT_LOTS` (= `[WORKCENTERNAME, EQUIPMENTNAME, FINISHEDRUNCARD, PJ_WORKORDER, CONTAINERNAME, PJ_TYPE, PJ_BOP, WAFER_LOT_ID]`) and `_PARTIAL_NONKEY_COLS_ADJACENT_LOTS` (= `[EQUIPMENTNAME, SPECNAME, FINISHEDRUNCARD, PJ_WORKORDER, CONTAINERNAME, PJ_TYPE, PJ_BOP, WAFER_LOT_ID]`). Add public function `aggregate_partial_trackouts(df, key_cols, nonkey_cols, *, query_id=None) -> DataFrame` modelled on `_pandas_aggregate_partial_trackouts` in `production_history_sql_runtime.py` (lines 406–496). Aggregates: `TRACKINQTY=MAX`, `TRACKOUTQTY=SUM`, `TRACKOUTTIMESTAMP=MAX`, `partial_count=COUNT(*)`. Strict guard: when any `nonkey_col` has `nunique(dropna=False) > 1` within a group, emit raw rows with `partial_count=1` instead of merging. Emit one `logger.info(...)` per call when divergent groups > 0. Preserve a stable sort: `TRACKINTIMESTAMP ASC NULLS LAST, CONTAINERID` for the lot/equipment paths; for adjacent_lots preserve the input order so the outer SQL's `rn` ordering still applies. | backend-engineer |
| IP-5 | Python — `query_tool_service.py` (lot_history paths) | In `get_lot_history` (line 1043) and `get_lot_history_batch` (line 1171, plus `_fetch_domain_records(..., "history")`-fed paths): after the rows are returned from `EventFetcher.fetch_events` and merged into the per-CID list (but BEFORE `_paginate_rows` and BEFORE `_store_query_tool_batch_spool`), call `aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT_HISTORY, query_id=...)`. Convert back to records of dicts for downstream `_paginate_rows` and `_enrich_workcenter_group`. The `total` returned to the API must be the post-aggregation row count (mirrors PH-06 contract). | backend-engineer |
| IP-6 | Python — `query_tool_service.py` (adjacent_lots) | In `get_adjacent_lots` (line 1112), AFTER `df = read_sql_df_slow(sql, params)` and BEFORE `_df_to_records(df)`: apply `aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_3, _PARTIAL_NONKEY_COLS_ADJACENT_LOTS, query_id=None)`. RATIONALE: Oracle's `RELATIVE_POSITION` is already computed from per-partial raw rows — but partials of a single trackin share `TRACKINTIMESTAMP` so they all receive THE SAME `rn` (the outer `ROW_NUMBER` partitions by `EQUIPMENTID` and orders by `TRACKINTIMESTAMP` — ties on identical TRACKINTIMESTAMP). After Python aggregation, one row per group survives carrying that `rn`; the `RELATIVE_POSITION = r.rn - t.target_rn` arithmetic remains valid. Verify with `TestAdjacentLotsRelativePosition` (test-plan.md). | backend-engineer |
| IP-7 | Python — `query_tool_service.py` (equipment_lots) | In `get_equipment_lots` (line 2363), AFTER `df = read_sql_df_slow(sql, params)` and BEFORE `_df_to_records` / `_paginate_rows`: call `aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_EQUIPMENT_LOTS, query_id=None)`. | backend-engineer |
| IP-8 | Tests — new file | Create `tests/test_query_tool_partial_trackout.py` with the test classes and test names enumerated in `test-plan.md §Test Names`. Use `SQLLoader.load("query_tool/<file>")` + substring/regex checks for the SQL-structure family; build pandas DataFrame fixtures (with decrementing TRACKINQTY per `test-plan.md §Fixture Discipline`) and call `aggregate_partial_trackouts` directly for aggregation / strict-guard / decrementing-qty / API-shape families; read `contracts/business/business-rules.md` and `contracts/data/data-shape-contract.md` as text for `TestContractFilePresence`. | backend-engineer |
| IP-9 | Tests — extend existing | Add `TestTryComputePageFromSpool::test_partial_count_present_in_returned_data` in `tests/test_query_tool_sql_runtime.py` per `test-plan.md §Extend vs Create`. Fixture is a parquet spool DataFrame containing a `partial_count` column with at least one row where `partial_count >= 2`. Verify `try_compute_page_from_spool` returns rows that preserve `partial_count`. | backend-engineer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| change-request.md | "Original Request" + "Currently all three SQL files use ROW_NUMBER..." | scope and exact bug |
| change-classification.md | §Inferred Acceptance Criteria AC-1 … AC-8 | acceptance criteria the implementation must satisfy |
| change-classification.md | §Clarifications/Assumptions 2, 3, 4 | adjacent_lots 3-tuple rationale; reference implementation; spool path nuance |
| test-plan.md | §Acceptance Criteria → Test Mapping | which tests cover which AC |
| test-plan.md | §Test Names | exact test class/method names to create |
| test-plan.md | §Fixture Discipline | decrementing-TRACKINQTY arithmetic that every per-file fixture must satisfy |
| test-plan.md | §Notes | strict-guard column lists per SQL file |
| ci-gates.md | §Required Gates `unit-mock-integration` row | command to run before PR |
| ci-gates.md | §Rollback Policy | confirms no spool parquet cleanup needed |
| contracts/business/business-rules.md | QT-05 (line 158) | aggregation contract (4-tuple / 3-tuple, MAX/SUM, partial_count) |
| contracts/business/business-rules.md | QT-06 (line 159) | strict-guard contract + per-file non-key column lists + INFO log format |
| contracts/business/business-rules.md | PH-01 / PH-06 / PH-07 | semantic precedent shared with production-history |
| contracts/data/data-shape-contract.md | §3.6 (line 374) | row shape for lot-history / equipment-lots / adjacent-lots responses incl. `partial_count` |
| src/mes_dashboard/services/production_history_sql_runtime.py | lines 195–250 (DuckDB CTE) | reference CTE structure for divergent-group split (informational; query-tool does not use the DuckDB CTE path) |
| src/mes_dashboard/services/production_history_sql_runtime.py | lines 386–496 (`_PARTIAL_KEY_COLS`, `_PARTIAL_NONKEY_COLS`, `_pandas_aggregate_partial_trackouts`) | canonical pandas aggregation pattern to mirror |
| src/mes_dashboard/services/event_fetcher.py | `_build_domain_sql(...)` `domain == "history"` branch (line 194) | confirms `lot_history.sql` is the SQL backing both `get_lot_history` and `get_lot_history_batch` via EventFetcher |

## File-Level Plan

| path | action | notes |
|---|---|---|
| `src/mes_dashboard/sql/query_tool/lot_history.sql` | edit (IP-1) | Remove `ROW_NUMBER` window in `ranked_history` CTE and outer `WHERE rn = 1`. Final SELECT projects raw rows; ORDER BY preserved; `{{ WORKCENTER_FILTER }}` placeholder preserved. |
| `src/mes_dashboard/sql/query_tool/equipment_lots.sql` | edit (IP-2) | Same shape as IP-1. Preserve `{{ EQUIPMENT_FILTER }}`, date binds, and final ORDER BY. |
| `src/mes_dashboard/sql/query_tool/adjacent_lots.sql` | edit (IP-3) | Drop `dedup_rn` window inside `raw_lots`; drop the `deduped_lots` CTE; `ranked_lots /*+ MATERIALIZE */` selects directly `FROM raw_lots`. Outer `rn`, `target_lot`, `first_diff_before/after`, and `RELATIVE_POSITION` arithmetic remain unchanged. |
| `src/mes_dashboard/services/query_tool_sql_runtime.py` | edit (IP-4, IP-9-fixture support) | Add `_PARTIAL_KEY_COLS_*`, `_PARTIAL_NONKEY_COLS_*` constants, `aggregate_partial_trackouts(...)` function. Existing `try_compute_page_from_spool` does `SELECT *` so `partial_count` flows through automatically — no changes needed there. |
| `src/mes_dashboard/services/query_tool_service.py` | edit (IP-5, IP-6, IP-7) | Call `aggregate_partial_trackouts(...)` in `get_lot_history`, `get_lot_history_batch`, `get_adjacent_lots`, `get_equipment_lots` between Oracle fetch and pagination/spool. `total` becomes post-aggregation count. |
| `tests/test_query_tool_partial_trackout.py` | create (IP-8) | All test names from `test-plan.md §Test Names`. Tier-0 (no Oracle). |
| `tests/test_query_tool_sql_runtime.py` | edit (IP-9) | Append `TestTryComputePageFromSpool::test_partial_count_present_in_returned_data`. |

## Contract Updates

- API: No JSON field renames or removals. `partial_count` is additive per `contracts/api/api-contract.md` and QT-05; treat as already-specified.
- CSS/UI: none.
- Env: none.
- Data shape: `contracts/data/data-shape-contract.md §3.6` already enumerates `partial_count` and the three query-tool surfaces (verified). No further edits required from backend-engineer.
- Business logic: `contracts/business/business-rules.md` rows QT-05 (line 158) and QT-06 (line 159) already enumerate the 4-tuple / 3-tuple keys, MAX/SUM aggregation, strict-guard column lists, and INFO-log format. No further edits required from backend-engineer; the contract was finalized by `contract-reviewer` (see `agent-log/contract-reviewer.yml`).
- CI/CD: none. `ci-gates.md §CI/CD Workflow` confirms no new workflow files.

## Test Execution Plan

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | `tests/test_query_tool_partial_trackout.py::TestLotHistorySqlStructure` + `TestLotHistoryAggregation` | All 9 tests pass; lot_history.sql contains no `ROW_NUMBER(`, no `WHERE rn = 1`; aggregation returns `partial_count=2`, `TRACKINQTY=99424`, `TRACKOUTQTY=99424` for the decrementing fixture. |
| AC-2 | `tests/test_query_tool_partial_trackout.py::TestEquipmentLotsSqlStructure` + `TestEquipmentLotsAggregation` | All 6 tests pass; equipment_lots.sql contains no `ROW_NUMBER(`. |
| AC-3 | `tests/test_query_tool_partial_trackout.py::TestAdjacentLotsSqlStructure` + `TestAdjacentLotsAggregation` + `TestAdjacentLotsRelativePosition` | Inner `dedup_rn` removed; outer `ROW_NUMBER() OVER (PARTITION BY ... EQUIPMENTID ORDER BY ... TRACKINTIMESTAMP)` preserved; `RELATIVE_POSITION = 0` for target after aggregation. |
| AC-4 | `tests/test_query_tool_partial_trackout.py::TestStrictGuardLotHistory` / `TestStrictGuardEquipmentLots` / `TestStrictGuardAdjacentLots` | Divergent non-key column triggers raw rows with `partial_count=1`; no merge. INFO log emitted exactly once per affected aggregate call. |
| AC-5 | `tests/test_query_tool_partial_trackout.py::TestDecrementingTrackinQty::*` | All 3 tests pass with TRACKINQTY=99424, TRACKOUTQTY=99424, partial_count=2. |
| AC-6 | (verified by AC-5 fixture discipline) | Same as AC-5; fixture explicitly differs across partials per `test-plan.md §Fixture Discipline`. |
| AC-7 | `tests/test_query_tool_partial_trackout.py::TestApiResponseShape` + `tests/test_query_tool_sql_runtime.py::TestTryComputePageFromSpool::test_partial_count_present_in_returned_data` | API response includes `partial_count`; existing field names (`TRACKINQTY`, `TRACKOUTQTY`) unchanged. |
| AC-8 | `tests/test_query_tool_partial_trackout.py::TestContractFilePresence` | business-rules.md QT-05 / QT-06 present; data-shape-contract.md §3.6 mentions `partial_count` for query-tool. |

Single pre-PR command (from `ci-gates.md`):

```
conda run -n mes-dashboard pytest tests/test_query_tool_partial_trackout.py tests/test_query_tool_sql_runtime.py -v
```

Lint + full Tier-1 gate (`ci-gates.md §Required Gates`):

```
ruff check .
conda run -n mes-dashboard pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x
```

Contract validate:

```
cdd-kit validate
```

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- Strict guard is applied in Python, not Oracle SQL (the canonical pattern in `production_history_sql_runtime.py` keeps both the DuckDB-CTE and pandas-groupby strict guards in Python — Oracle SQL is reserved for raw row fetch). Do not attempt to encode the strict guard as Oracle `GROUP BY ... HAVING COUNT(DISTINCT ...) = 1`; it is more fragile and obscures the divergent-row fallback than the pandas path.
- The Oracle fetch must NOT pre-aggregate (e.g., do not add `GROUP BY` + `MAX/SUM` in Oracle). Aggregation must run in Python so the strict guard can emit raw rows on divergence — a pre-aggregated Oracle result destroys per-partial rows and cannot satisfy AC-4.
- For `adjacent_lots.sql`, do NOT alter the outer `ranked_lots /*+ MATERIALIZE */ ROW_NUMBER()` window, `target_lot` CTE, `first_diff_before/after` CTEs, or the `RELATIVE_POSITION = r.rn - t.target_rn` arithmetic. Only the inner `dedup_rn` is removed.
- Spool TTL and namespace constants in `query_tool_service.py` (`QUERY_TOOL_SPOOL_NS_HISTORY_BATCH`, `QUERY_TOOL_SPOOL_TTL_SECONDS`) are unchanged.
- API JSON field names (`TRACKINQTY`, `TRACKOUTQTY`, `TRACKINTIMESTAMP`, `TRACKOUTTIMESTAMP`, etc.) are unchanged. Only `partial_count` is additive.

## Known Risks

- **Spool TTL collision after deploy.** Any spool entries written before the deploy lack the `partial_count` column. `try_compute_page_from_spool` does `SELECT *` so the page response will be missing `partial_count`. Mitigation: TTL (≥ 60 s, configurable via `QUERY_TOOL_SPOOL_TTL_SECONDS`) ages out old spools naturally; no explicit cleanup required because spools are short-lived and per-query-hash. Documented as informational in `ci-gates.md §Rollback`.
- **`adjacent_lots` ordering tie-break.** The outer `ROW_NUMBER() OVER (PARTITION BY EQUIPMENTID ORDER BY TRACKINTIMESTAMP)` assigns equal `rn` to rows sharing `TRACKINTIMESTAMP` in Oracle (deterministic tie-break is implementation-defined). Once Python aggregation collapses each group to one row, the one surviving `rn` is whatever Oracle assigned to one of the tied partials — `RELATIVE_POSITION` arithmetic still holds because the target also has the tied `rn`. Test `TestAdjacentLotsRelativePosition::test_neighbors_have_correct_relative_positions_after_aggregation` covers this.
- **Strict-guard non-key column drift.** If future changes to `lot_history.sql` add a new projected column (e.g., a JOIN extension), it must be added to `_PARTIAL_NONKEY_COLS_LOT_HISTORY` (or accepted as an aggregation no-op via `ANY_VALUE` semantics). Add a comment block in `query_tool_sql_runtime.py` next to the constant explaining the contract obligation.
- **Total-row count semantic change.** `get_lot_history(...)['total']` and `get_equipment_lots(...)['total']` will drop from per-partial count to per-group count post-deploy. This is the correct semantic (matches PH-01 / PH-06) and matches the API contract `partial_count` field, but any frontend assertion that counted "expected raw-partial count" will fail. Confirm no such assertions exist (search frontend specifications under context-manifest; out of scope to edit frontend code).

