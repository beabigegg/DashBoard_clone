## Context

The reject-history spool pipeline stores query results as parquet files using the `performance_daily_lot.sql` base query. This query operates at per-LOT granularity — each row contains a `CONTAINERID` column and represents one LOT-day-workcenter-reason combination. At this level, `AFFECTED_LOT_COUNT` is not pre-aggregated (unlike `performance_daily.sql` which groups across LOTs and computes `COUNT(DISTINCT CONTAINERID)`).

The DuckDB spool runtime in `reject_cache_sql_runtime.py` has a column-presence check pattern: if a column exists in the parquet, use it; otherwise fall back to `"0"`. For `AFFECTED_LOT_COUNT`, the column is never present in per-LOT parquet, so the fallback always produces 0.

The frontend DuckDB composable (`useRejectHistoryDuckDB.js:146`) already handles this correctly by using `COUNT(DISTINCT CONTAINERID)`.

## Goals / Non-Goals

**Goals:**
- Fix `AFFECTED_LOT_COUNT` to show the correct distinct LOT count in the reject-history summary card
- Apply the fix to both code paths in `reject_cache_sql_runtime.py`: view analytics and batch-pareto

**Non-Goals:**
- Changing the parquet schema or spool pipeline (the per-LOT granularity is correct by design)
- Modifying the frontend DuckDB composable (already correct)
- Changing `performance_daily_lot.sql` or `primary.sql`

## Decisions

**Decision: Use `COUNT(DISTINCT "CONTAINERID")` as fallback when `AFFECTED_LOT_COUNT` column is absent**

The column-presence check pattern remains: if `AFFECTED_LOT_COUNT` exists in cols, use `SUM(...)` as before (for compatibility with any future pre-aggregated data). If it doesn't exist but `CONTAINERID` does, use `COUNT(DISTINCT "CONTAINERID")`. Only fall back to `"0"` if neither column is available.

Rationale: This mirrors the frontend approach, preserves backward compatibility, and correctly handles the per-LOT parquet schema.

## Risks / Trade-offs

- **[Low] Performance of COUNT(DISTINCT)**: `COUNT(DISTINCT "CONTAINERID")` on DuckDB over parquet is efficient — DuckDB handles distinct counts well even on large datasets. No measurable impact expected.
- **[None] API compatibility**: The response field `AFFECTED_LOT_COUNT` already exists in the contract. Only its value changes from 0 to the correct count.
