# ADR 0005: resource-history canonical spool key excludes granularity and filters

## Status
proposed

## Context
`/api/resource/history/query` toggles day/week/month/year granularity and several
filter dimensions (workcenter group, family, resource, package group, prod/key/monitor
flags). Two spool-key systems coexisted and never connected:

- System A (`execute_primary_query`): key = hash(date-range + granularity + all filters).
  Every filter combination is a separate Oracle query; this is the only path that
  ever wrote spool.
- System B (`try_compute_query_from_canonical_spool` + `make_canonical_base_query_id`):
  key = hash(schema_version + date-range + granularity). Filters are applied at DuckDB
  view time via INNER JOIN on `resource_dim`. This path read a key no writer ever
  produced (warmup's `ensure_dataset_loaded` checked the canonical key but delegated to
  `execute_primary_query`, which wrote the System A key), so it always returned SPOOL_MISS.

The source `base_facts.sql` stores daily shift-hours per equipment (HISTORYID + TXNDATE);
granularity bucketing is computed in DuckDB `_granularity_bucket_expr`, not in the spool.

## Decision
The canonical spool key for resource-history is hash(schema_version + start_date + end_date)
— **granularity and filters are both excluded**. One day-level parquet serves every
granularity and every filter combination, derived at DuckDB view time. `_CANONICAL_BASE_SCHEMA_VERSION`
is bumped (1 → 2) so existing granularity-bearing parquet is invalidated by key change.
This mirrors ADR-0001 (material-consumption) for the same reason.

## Consequences
- Granularity and filter switches on a warm date range cost zero Oracle round-trips.
- Future engineers must not re-add `granularity` or any filter dimension to the canonical
  key — doing so multiplies spool count and silently re-introduces per-toggle Oracle queries.
- The schema_version bump requires post-deploy `rm` of orphaned parquet under
  `tmp/query_spool/resource_dataset/` and `tmp/query_spool/resource_oee/` (Redis pointers
  expire by TTL; disk files do not self-clean).
- System A (filter-inclusive key) remains as the Oracle-fetch fallback for first queries and
  out-of-window ranges; its deprecation is deferred to a follow-up change.
