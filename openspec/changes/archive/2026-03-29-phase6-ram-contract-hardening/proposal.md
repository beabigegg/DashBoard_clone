## Why

Phase 1 through Phase 5 have largely moved heavy historical queries to the spool-first and DuckDB-first runtime, but the implementation still has three contract gaps that weaken the rollout. MSD view endpoints still auto-dispatch work on spool miss, Type A primary queries can mask runtime failures as empty success payloads, and WIP Parquet cache observability still disagrees on the canonical Redis key.

## What Changes

- Tighten the Type B contract for MSD so detail and export endpoints return `410 cache_expired` on spool miss and never enqueue work from the view layer.
- Harden Type A synchronous bootstrap semantics for `resource-history` and `hold-history` so primary query failures in the DuckDB/view stage are surfaced as failures instead of `200` empty results.
- Normalize WIP Parquet key handling so updater, reader, health checks, and admin telemetry all inspect the same canonical Redis key.
- Add verification coverage for contract-consistent error semantics and cache observability alignment.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `query-response-semantic-contract`: clarify that Type B MSD view endpoints must return `410 cache_expired` without auto-dispatch and that Type A bootstrap must not synthesize empty success payloads on runtime failure.
- `msd-async-analysis`: require MSD detail and export routes to behave as pure Type B view endpoints on spool miss.
- `resource-dataset-cache`: require synchronous bootstrap to fail explicitly when a just-produced spool cannot be rendered by DuckDB.
- `hold-dataset-cache`: require synchronous bootstrap to fail explicitly when a just-produced spool cannot be rendered by DuckDB.
- `wip-cache-parquet-only`: require canonical single-prefix Redis key usage for WIP Parquet read/write and availability checks.
- `cache-observability-hardening`: require admin and health telemetry to report against the same canonical WIP Parquet key used by the runtime.

## Impact

Affected areas include MSD analysis/detail/export routes, resource and hold dataset cache services, WIP cache updater and reader paths, and admin/health observability endpoints. API behavior changes are limited to error semantics on cache/runtime miss paths and do not introduce new endpoints or dependencies.
