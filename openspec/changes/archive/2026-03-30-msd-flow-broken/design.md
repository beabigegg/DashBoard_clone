## Context

Commit `c884e877` introduced a spool-first path for MSD detail/export endpoints. The frontend already captures `currentTraceQueryId` from the events stage (App.vue:446) and passes it for CSV export (App.vue:503), but `buildDetailParams()` omits it. This single omission causes the detail endpoint to resolve a `trace_query_id` internally with no matching spool, resulting in 410.

## Goals / Non-Goals

**Goals:**
- Restore MSD detail table loading by passing `trace_query_id` from frontend to detail endpoint

**Non-Goals:**
- Adding legacy Oracle fallback paths (contradicts the spool→DuckDB migration direction)
- Changing backend endpoint logic — it already works correctly when `trace_query_id` is provided

## Decisions

### D1: Frontend passes `trace_query_id` in detail calls

`buildDetailParams()` will include `trace_query_id: currentTraceQueryId.value` when available, identical to how `exportCsv()` already does it at line 503. This is the only fix needed.

**Alternative considered**: Add backend fallback to legacy Oracle query. Rejected — recent architecture direction is spool→DuckDB, removing pandas/Oracle paths. A fallback would be going backwards.

## Risks / Trade-offs

- **[Spool expiry between events and detail]** → If the spool expires in the brief window between events completion and detail request, the 410 will still occur. This is an edge case that can be addressed separately if observed.
