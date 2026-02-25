## Why

Hold-history and resource-history pages currently fire 4 separate Oracle queries per user interaction (filter change, pagination, refresh), all hitting the same base table with identical filter parameters. This wastes Oracle connections and creates unnecessary latency — especially now that these pages use `read_sql_df_slow` (dedicated connections with 300s timeout). The reject-history page already solves this with a "single query + cache derivation" pattern that reduces Oracle load by ~75%. Hold-history and resource-history should adopt the same architecture.

## What Changes

- **New `hold_dataset_cache.py`**: Two-phase cache module for hold-history. Single Oracle query caches the full hold/release fact set; subsequent views (trend, reason pareto, duration distribution, paginated list) are derived from cache using pandas.
- **New `resource_dataset_cache.py`**: Two-phase cache module for resource-history. Single Oracle query caches the full shift-status fact set; subsequent views (KPI, trend, heatmap, workcenter comparison, paginated detail) are derived from cache using pandas.
- **Hold-history route rewrite**: Replace 4 independent GET endpoints with POST /query (primary) + GET /view (supplementary) pattern.
- **Resource-history route rewrite**: Replace GET /summary (3 parallel queries) + GET /detail (1 query) with POST /query + GET /view pattern.
- **Frontend two-phase flow**: Both pages adopt queryId-based flow — primary query returns queryId + initial view; filter/pagination changes call GET /view with queryId (no Oracle).
- **Cache infrastructure**: L1 (ProcessLevelCache, in-process) + L2 (Redis, parquet/base64), 15-minute TTL, deterministic query ID from SHA256 of primary params. Same architecture as `reject_dataset_cache.py`.

## Capabilities

### New Capabilities
- `hold-dataset-cache`: Two-phase dataset cache for hold-history (single Oracle query + in-memory derivation for trend, reason pareto, duration, paginated list)
- `resource-dataset-cache`: Two-phase dataset cache for resource-history (single Oracle query + in-memory derivation for KPI, trend, heatmap, comparison, paginated detail)

### Modified Capabilities
- `hold-history-api`: Route endpoints change from 4 independent GETs to POST /query + GET /view
- `hold-history-page`: Frontend adopts two-phase queryId flow
- `resource-history-page`: Frontend adopts two-phase queryId flow; route endpoints consolidated

## Impact

- **Backend**: New files `hold_dataset_cache.py`, `resource_dataset_cache.py`; modified routes for both pages; service functions remain but are called only once per primary query
- **Frontend**: `hold-history/App.vue` and `resource-history/App.vue` rewritten for two-phase flow
- **Oracle load**: ~75% reduction per page (4 queries → 1 per user session, subsequent interactions from cache)
- **Redis**: Additional cache entries (~2 namespaces, same TTL/encoding as reject_dataset)
- **API contract**: Endpoint signatures change (breaking for these 2 pages, but no external consumers)
