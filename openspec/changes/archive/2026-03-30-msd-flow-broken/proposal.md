## Why

Commit `c884e877` (2026-03-27) changed MSD detail/export endpoints to require a `trace_query_id` backed by a DuckDB spool file. However, the frontend `buildDetailParams()` never passes the `currentTraceQueryId` it captures from the events stage. The backend falls back to resolving a `trace_query_id` internally, but no spool file exists (because the frontend completed seed→lineage→events but the spool may not match), causing a 410 `cache_expired_error`. This breaks the entire MSD detail table flow.

## What Changes

- **Fix `buildDetailParams()`** in `App.vue` to include `trace_query_id` from `currentTraceQueryId` when available, matching how `exportCsv()` already does it (line 503).

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `progressive-trace-ux`: The detail call chain must pass `trace_query_id` from the events stage result to downstream API calls.

## Impact

- **Frontend**: `frontend/src/mid-section-defect/App.vue` — `buildDetailParams()` function
- **No backend changes needed**: the spool path works correctly when `trace_query_id` is provided
