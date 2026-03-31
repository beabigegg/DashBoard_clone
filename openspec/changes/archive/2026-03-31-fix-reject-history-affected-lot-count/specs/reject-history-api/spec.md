## ADDED Requirements

### Requirement: DuckDB spool runtime SHALL derive AFFECTED_LOT_COUNT from CONTAINERID

When the spool parquet file uses per-LOT granularity (i.e., `CONTAINERID` column is present but `AFFECTED_LOT_COUNT` column is absent), the DuckDB spool runtime SHALL compute `AFFECTED_LOT_COUNT` as `COUNT(DISTINCT "CONTAINERID")` instead of falling back to literal `0`.

This applies to both the view analytics query and the batch-pareto query in `reject_cache_sql_runtime.py`.

#### Scenario: Per-LOT parquet without AFFECTED_LOT_COUNT column
- **WHEN** the spool parquet contains `CONTAINERID` but does not contain `AFFECTED_LOT_COUNT`
- **THEN** the system SHALL use `COUNT(DISTINCT "CONTAINERID")` to compute the affected LOT count in analytics and pareto queries

#### Scenario: Pre-aggregated parquet with AFFECTED_LOT_COUNT column
- **WHEN** the spool parquet contains an `AFFECTED_LOT_COUNT` column
- **THEN** the system SHALL use `SUM(COALESCE("AFFECTED_LOT_COUNT", 0))` as before (backward compatibility)

#### Scenario: Parquet with neither CONTAINERID nor AFFECTED_LOT_COUNT
- **WHEN** the spool parquet contains neither `CONTAINERID` nor `AFFECTED_LOT_COUNT`
- **THEN** the system SHALL fall back to literal `0`
