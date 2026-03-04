## Why

The reject-history Pareto workflow currently recomputes aggregates from full lot-level cached datasets on every interactive filter change. Under wide date ranges and cross-filtering, this drives repeated high-memory pandas operations and can destabilize workers.

## What Changes

- Introduce a materialized Pareto aggregate layer for reject-history that precomputes dimension metrics from cached query datasets.
- Serve `/api/reject-history/batch-pareto` and related Pareto reads from pre-aggregated artifacts instead of recomputing from full detail rows each request.
- Add freshness/version metadata so aggregate snapshots stay aligned with source query datasets and policy toggles.
- Add bounded invalidation and lifecycle rules for aggregate artifacts to avoid stale growth and memory pressure.
- Add observability for aggregate build latency, hit ratio, memory footprint, and fallback reasons.
- Keep API response schema compatible with existing frontend contracts to avoid UI rewrites.

## Capabilities

### New Capabilities
- `reject-history-pareto-materialized-aggregate`: Build, store, and read pre-aggregated Pareto data for interactive cross-filter workflows.

### Modified Capabilities
- `reject-history-api`: Route Pareto endpoints to materialized aggregates with cache-consistency and fallback behavior.
- `cache-observability-hardening`: Extend telemetry to cover aggregate generation/hit/fallback and memory-guard events.

## Impact

- Affected backend code:
  - `src/mes_dashboard/services/reject_dataset_cache.py`
  - `src/mes_dashboard/services/reject_history_service.py`
  - `src/mes_dashboard/routes/reject_history_routes.py`
  - new aggregate builder/storage modules under `src/mes_dashboard/services/`
- Affected APIs:
  - `/api/reject-history/batch-pareto`
  - `/api/reject-history/reason-pareto` (cache-backed path)
- Affected runtime systems:
  - Process L1 cache, Redis/L2 cache, spool lifecycle and metrics history
- Dependencies/ops:
  - Additional Redis key space and retention policy tuning for aggregate artifacts
  - New monitoring/alerts for aggregate freshness and fallback rates
