## Why

The current cache and query architecture mixes multiple storage and execution models across gunicorn memory, Redis, Parquet spool, DuckDB runtime, and RQ job state. This causes repeated Oracle fallback, duplicated memory residency, inconsistent TTL/refresh behavior, and uneven handling between realtime snapshots, heavy history queries, trace flows, and derived anomaly results.

This change is needed now because the project has already adopted DuckDB and Parquet spool in several high-volume paths, but the system still lacks a single contract for where data should live, how it should refresh, and which layers are allowed to retain large payloads. Without that contract, more features will continue to drift into inconsistent cache behavior and memory usage.

## What Changes

- Define a global cache/query architecture with four planes: `snapshot`, `heavy-query`, `derived-result`, and `control`.
- Standardize realtime datasets such as WIP, resource master, realtime equipment status, and filter caches to use Redis-backed snapshot storage without large gunicorn L1 payload caches.
- Standardize history, trace, export, and large-detail queries to use `Oracle -> Parquet spool -> DuckDB runtime`, with Redis limited to metadata, state, locks, progress, and lightweight indexes.
- Require heavy-query runtimes to use a shared DuckDB runtime contract with bounded memory/thread settings and no pandas fallback as the primary view path.
- Move trace and lineage result storage away from large Redis JSON payloads toward spool-backed results where the result set is heavy or replayable.
- Clarify that anomaly computation is a derived-result layer that consumes canonical source datasets, rather than acting as an implicit source-dataset warmup mechanism.
- **BREAKING**: Disallow large in-process dataset caches in gunicorn workers for cache domains covered by the new architecture.
- **BREAKING**: Restrict Redis result payload storage for heavy-query domains to metadata/state/index use, not full query result bodies.

## Capabilities

### New Capabilities
- `cache-plane-architecture`: Defines the system-wide contract for snapshot storage, heavy-query storage, derived-result caching, and control-plane metadata boundaries.

### Modified Capabilities
- `dataset-cache-metadata-only-redis`: Extend metadata-only Redis requirements from selected dataset caches to the broader heavy-query contract.
- `parquet-spool-view-engine`: Standardize DuckDB-over-Parquet as the canonical runtime for heavy-query views, exports, and replayable result access.
- `wip-cache-parquet-only`: Use the WIP snapshot model as the canonical Redis snapshot baseline for realtime datasets.
- `resource-cache-representation-normalization`: Change resource master cache behavior to align with snapshot-plane rules and remove long-lived in-process derived payload ownership.
- `anomaly-summary-api`: Reframe anomaly computation as a derived-result consumer of canonical source datasets, not a source warmup owner.
- `trace-staged-api`: Change staged trace result persistence rules so large lineage/event results follow heavy-query storage rules instead of Redis body storage.
- `material-trace-api`: Tighten material-trace requirements so replayable query results are served from spool-backed heavy-query storage.
- `query-tool-equipment`: Route historical equipment-hour and related large history-style queries through heavy-query storage instead of Redis payload caching.

## Impact

- Affected backend systems: `cache_updater`, `resource_cache`, `realtime_equipment_cache`, `query_spool_store`, DuckDB SQL runtimes, trace job services, anomaly scheduler/runtime, query-tool history paths, material trace, production history, job query, and dataset cache modules.
- Affected operational systems: Redis topology and eviction policy, RQ/control-plane isolation, spool retention policy, DuckDB runtime configuration, and cache observability.
- Affected APIs: history/query/export endpoints that currently rely on mixed Redis payload, in-memory cache, or direct-Oracle behavior may shift to canonical spool-backed result lifecycle semantics.
