# ADR 0013: DB-scheduling reuses the WIP cache view, no dedicated Oracle query or endpoint cache

## Status
proposed

## Context
The DB生產排程助手 endpoint (`GET /api/db-scheduling/queue`) needs two slices of
`DWH.DW_MES_LOT_V`: the `D/B-START` source lots and the currently-ACTIVE
equipment running at the 12 DB-process SPECs (DB-00). A validated standalone SQL
(`WITH start_lots ... LEFT JOIN running_eqp ...`) exists and was tested against
production Oracle. That same view is already loaded, in full, into a Redis-backed
5-minute WIP cache (`get_cached_wip_data()`), which is the substrate every other
WIP-derived feature reads. There are therefore two viable data-flows: run the
dedicated SQL against Oracle per request, or derive both slices from the existing
cached DataFrame in pandas. Business rule DB-05 and data-shape §3.22 both already
pin the source as "the existing 5-min WIP cache."

## Decision
Derive both the start-lots and the running-equipment pool from the existing WIP
cache DataFrame in `db_scheduling_service`, performing the workflow match (DB-02),
BOP-first-char fallback (DB-03), and sort (DB-04) in Python. Use a direct
`read_sql_df` only as a cache-miss fallback. Do NOT add a dedicated per-request
Oracle JOIN as the primary path, and do NOT add an endpoint-level Redis cache.

## Consequences
- Single source of truth for the view: one 5-minute snapshot, one staleness
  window. The page can never disagree with WIP/Hold/other cache consumers.
- No extra Oracle round-trip per page load; the only expensive I/O is the cache
  refresh that already runs for WIP.
- The validated standalone SQL remains in the spec as the semantic reference for
  the pandas implementation, not as runtime code — the BOP fallback's
  "only when primary match is empty" precedence stays explicit in sequential
  Python rather than collapsing into a second self-JOIN.
- This is a deliberate capability choice that must not be silently reversed:
  re-introducing a dedicated Oracle query or a second endpoint cache would create
  a second, independently-stale snapshot of the same view and reintroduce the
  staleness-confusion this ADR avoids (and would duplicate the DB-00 SPEC list
  into SQL). Any future move to a dedicated query must be justified by a measured
  cache-coverage or freshness gap, not convenience.
- CI has no Redis; the cache-miss fallback path must be covered so the service
  degrades to `read_sql_df` (or an empty result) instead of 500ing.
- No new DB object, queue, cache namespace, or parquet schema; rollback is a pure
  code revert.
