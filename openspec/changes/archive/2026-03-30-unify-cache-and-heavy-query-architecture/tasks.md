## 1. Architecture Foundations

- [x] 1.1 Introduce shared cache-plane terminology and architecture constants/utilities for `snapshot`, `heavy-query`, `derived-result`, and `control`
- [x] 1.2 Add a shared heavy-query metadata contract for canonical query identity, spool metadata, inflight state, and lightweight stage/index manifests
- [x] 1.3 Introduce a shared DuckDB runtime factory/policy that enforces common memory and thread limits across heavy-query runtimes
- [x] 1.4 Add observability for spool hits/misses, canonical query identities, and result-lifecycle failures across heavy-query modules

## 2. Snapshot Plane Normalization

- [x] 2.1 Refactor `resource_cache` to use Redis-backed canonical snapshot storage without long-lived gunicorn-owned full DataFrame/index caches
- [x] 2.2 Align `resource_cache` retention with `RESOURCE_SYNC_INTERVAL` so Redis expiry does not force routine Oracle fallback during healthy sync windows
- [x] 2.3 Refactor `realtime_equipment_cache` to match snapshot-plane ownership rules and remove long-lived authoritative worker-owned payload caches
- [x] 2.4 Verify WIP, resource, equipment, and filter caches all follow the same snapshot-plane publication and metadata model

## 3. Heavy-Query Plane Normalization

- [x] 3.1 Remove full-result Redis payload storage from covered heavy-query domains and keep Redis limited to metadata, lifecycle state, lightweight indexes, and locks
- [x] 3.2 Update heavy-query modules to use the shared DuckDB runtime policy for page, view, and export execution over canonical Parquet spool
- [x] 3.3 Normalize direct-path and chunked-path heavy-query writes so reusable result bodies always land in canonical Parquet spool
- [x] 3.4 Audit history/export/query-tool paths and route replayable or large history-style queries to the heavy-query plane

## 4. Trace and Material Query Migration

- [x] 4.1 Change trace events result persistence to canonical spool-backed heavy-query storage with Redis used only for job/progress/result metadata
- [x] 4.2 Change trace lineage result persistence to spool-backed storage for replayable or large lineage graphs while preserving existing API result shape
- [x] 4.3 Tighten material-trace query and export paths so pagination, replay, and export all use the same canonical spool-backed result identity
- [x] 4.4 Migrate query-tool equipment historical result caching away from Redis body caching to heavy-query storage for replayable or large result sets

## 5. Derived Result and Warmup Decoupling

- [x] 5.1 Refactor anomaly scheduling so anomaly computation consumes canonical source dataset identities instead of acting as the steady-state warmup owner
- [x] 5.2 Keep anomaly summary/detail as compact derived-result cache payloads and verify they do not substitute for source dataset lifecycle ownership
- [x] 5.3 Review warmup/background jobs and remove or reassign any responsibilities that belong to snapshot-plane refresh or heavy-query lifecycle instead

## 6. Redis Control-Plane Isolation

- [x] 6.1 Separate control-plane Redis keys (locks, inflight state, job status, progress) from data-plane cache payload eviction behavior
- [x] 6.2 Update startup/runtime configuration so cache-plane Redis policy and control-plane Redis policy are independently configurable
- [x] 6.3 Validate that RQ workers, async job services, and distributed locks do not rely on evictable cache payload storage semantics
- [x] 6.4 Document rollout, rollback, and operational verification steps for the new cache/query architecture
