# ADR-0001: material-consumption summary spool excludes granularity from cache key

**Status**: accepted  
**Change**: material-part-consumption

## Context

`/material-consumption` lets users toggle week/month/quarter granularity for trend charts. The source table `DW_MES_LOTMATERIALSHISTORY` has ~17.8M rows; re-querying Oracle on each toggle would impose multi-second UX latency on a pure presentation change.

## Decision

Store the summary spool at day-level `(txn_date, MATERIALPARTNAME, PJ_TYPE)` and re-group in DuckDB on `GET /view?granularity=`. The summary spool cache key **excludes granularity** — one spool serves all three granularity views.

## Consequences

- Granularity toggle is a sub-millisecond DuckDB regroup with zero Oracle load.
- Future engineers must not add `granularity` to the summary cache key (would multiply spool count 3× and re-introduce Oracle round-trips per toggle).
- Future engineers must not re-query Oracle on granularity change in the view endpoint.
- The day-level granularity is the finest unit; coarser buckets (week/month/quarter) are derived at view time, never stored.
