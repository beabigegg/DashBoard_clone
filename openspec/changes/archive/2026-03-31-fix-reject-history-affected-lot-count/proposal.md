## Why

The reject-history page's "受影響 LOT" summary card always displays 0. The backend DuckDB spool runtime tries to `SUM("AFFECTED_LOT_COUNT")` from the parquet file, but the spool uses the per-LOT base query (`performance_daily_lot.sql`) which has no pre-aggregated `AFFECTED_LOT_COUNT` column — each row already represents one distinct LOT via `CONTAINERID`. The column-missing fallback emits literal `0`. Meanwhile, `AFFECTED_WORKORDER_COUNT` works because it IS present in the per-LOT data.

## What Changes

- Fix the backend DuckDB spool runtime (`reject_cache_sql_runtime.py`) to compute `AFFECTED_LOT_COUNT` as `COUNT(DISTINCT "CONTAINERID")` instead of `SUM("AFFECTED_LOT_COUNT")` when the latter column is absent but `CONTAINERID` is available.
- This aligns with the frontend DuckDB composable (`useRejectHistoryDuckDB.js`) which already uses `COUNT(DISTINCT CONTAINERID)` correctly.
- Two code paths affected: the view analytics query and the batch-pareto query.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

(none — this is a bug fix in the existing implementation; the API contract already specifies `AFFECTED_LOT_COUNT` should reflect the correct count)

## Impact

- **Backend:** `src/mes_dashboard/services/reject_cache_sql_runtime.py` — two `lot_expr` assignments (view analytics ~line 701, batch pareto ~line 534)
- **Frontend:** No changes needed (already correct)
- **API:** No contract change — the field already exists, it will now return the correct value instead of 0
