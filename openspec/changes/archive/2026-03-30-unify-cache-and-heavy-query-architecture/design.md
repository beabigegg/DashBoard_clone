## Context

The codebase currently uses multiple overlapping persistence and execution patterns:

- Redis snapshot storage for WIP and several filter caches
- Redis JSON or Redis DataFrame payload storage for some realtime and historical domains
- Parquet spool plus DuckDB runtime for several heavy-query domains
- gunicorn in-process `ProcessLevelCache` or bespoke L1 caches for several services
- RQ-based async job metadata and result storage mixed into the same Redis deployment

This mixed model has produced predictable problems:

- repeated Oracle fallback when TTL and refresh cadence are misaligned
- duplicated memory residency when web workers retain large parsed datasets
- heavy-query result bodies sometimes living in Redis and sometimes on disk
- trace and lineage flows using large Redis JSON payloads even when replayable/spool-backed access is more appropriate
- anomaly computation acting as an implicit spool seeding path for source datasets

The architecture already contains the right primitives: Redis snapshot storage, Parquet spool, DuckDB runtime, RQ workers, and async job metadata. The design goal is to assign each primitive a single responsibility and remove ambiguous ownership.

## Goals / Non-Goals

**Goals:**
- Establish one system-wide architecture that covers realtime snapshots, historical queries, trace flows, exports, and derived anomaly computation.
- Minimize gunicorn memory residency by removing large long-lived in-process dataset caches from covered domains.
- Make `Parquet spool + DuckDB runtime` the canonical storage/execution path for replayable heavy-query results.
- Make Redis the canonical store for snapshot-plane data and for heavy-query metadata/state, not for large heavy-query result bodies.
- Separate derived-result behavior from source-dataset warmup behavior.
- Define rollout boundaries so the system can migrate incrementally without breaking stable API response contracts.

**Non-Goals:**
- Redesign frontend UX or change response shapes unless required by async/result-lifecycle semantics.
- Replace DuckDB with another execution engine.
- Remove Redis from the system; the design narrows Redis responsibilities instead of eliminating it.
- Rewrite every Oracle query; the proposal standardizes storage/runtime behavior around existing query logic.

## Decisions

### Decision: Classify all cache/query flows into four planes

The system will use four explicit planes:

- `snapshot plane`: canonical Redis-backed datasets refreshed in the background
- `heavy-query plane`: replayable historical/trace/export results stored as Parquet spool and queried by DuckDB
- `derived-result plane`: compact results computed from source datasets, typically stored in Redis
- `control plane`: locks, inflight state, progress, job status, and lightweight metadata

Rationale:
- The current problems are mostly ownership problems, not missing technology.
- This classification makes it obvious where each dataset should live and prevents future drift.

Alternatives considered:
- Keep domain-by-domain custom behavior. Rejected because it preserves current inconsistency.
- Collapse everything into Redis. Rejected because large result bodies increase memory pressure and duplicate worker parsing cost.
- Collapse everything into DuckDB-managed files. Rejected because realtime snapshots and control-plane state remain a better fit for Redis.

### Decision: gunicorn workers will not own large dataset caches for covered domains

For snapshot-plane and heavy-query-plane domains, web workers may keep only request-scope objects and small metadata/state. They will not own long-lived full DataFrames, large parsed JSON payloads, or large derived indexes as authoritative caches.

Rationale:
- DuckDB was introduced to reduce memory usage; retaining long-lived L1 dataset copies in gunicorn undermines that goal.
- OS page cache and Parquet reuse already provide effective lower-level reuse without per-worker duplication.

Alternatives considered:
- Keep small TTL L1 caches everywhere. Rejected because even short TTLs still duplicate large datasets across workers and complicate invalidation.
- Keep L1 only for “hot” domains. Rejected because operational hotness changes over time and becomes another tuning burden.

### Decision: Redis is the source of truth for snapshot-plane data, not for heavy-query result bodies

Realtime WIP, resource master, realtime equipment status, and filter caches will use Redis snapshot storage. Heavy-query domains will use Redis only for metadata, lifecycle state, small indexes, progress, and locks. Full heavy-query result bodies must live in Parquet spool.

Rationale:
- Snapshot datasets need fast multi-worker sharing and bounded freshness; Redis is appropriate.
- Heavy-query result bodies are large, replayable, and often better handled by Parquet plus DuckDB.

Alternatives considered:
- Keep heavy-query bodies in Redis Parquet blobs. Rejected because this still increases Redis memory footprint and shifts parsing cost to application workers.
- Move snapshot-plane datasets to Parquet spool too. Rejected because those datasets are reused broadly and need low-latency random access without heavy-query lifecycle semantics.

### Decision: Heavy-query plane will use a single canonical execution contract

The canonical flow for heavy-query domains is:

`Oracle -> chunk/direct extraction -> Parquet spool -> DuckDB page/view/export runtime`

Redis stores:
- canonical query identity
- spool metadata pointer
- inflight state
- async job metadata/progress
- optional lightweight indexes or stage manifests

Rationale:
- This is already the most successful pattern in the codebase for production-history and several dataset caches.
- It gives bounded memory usage and deterministic replay behavior.

Alternatives considered:
- Allow direct-Oracle view endpoints after primary query. Rejected because it defeats result reuse and increases Oracle load.
- Materialize heavy-query results back into pandas/Redis for pagination. Rejected because it reintroduces RAM duplication and large Redis payloads.

### Decision: Heavy-query DuckDB runtimes will share a single runtime policy

All heavy-query DuckDB runtimes will use a common connection factory or equivalent shared policy that sets:
- memory limit
- thread limit
- temp/spill policy where applicable
- common error semantics for spool miss/runtime failure

Rationale:
- Today anomaly runtime is governed, while several history runtimes are not.
- Shared runtime policy is necessary for predictable memory behavior across domains.

Alternatives considered:
- Keep each runtime independently tuned. Rejected because that reproduces current inconsistency.

### Decision: Anomaly computation is a derived-result consumer, not a source warmup owner

The anomaly layer will consume canonical source dataset identities and produce compact summary/detail results. It must not be the implicit owner of source spool seeding for user-facing datasets.

Rationale:
- Source dataset warmup and derived analytics are separate responsibilities.
- Keeping them separate makes failure modes clearer and prevents anomaly scheduling from masking source dataset lifecycle issues.

Alternatives considered:
- Continue using anomaly startup/daily refresh as source spool seeding. Rejected because it entangles two layers with different freshness expectations.

### Decision: Redis control-plane state must be isolated from data-plane eviction pressure

RQ job metadata, locks, inflight state, and progress records must not depend on the same eviction behavior as cache payloads. Deployment may use separate Redis DBs or separate Redis instances, but the control-plane keys must be isolated from `allkeys-lru` cache eviction.

Rationale:
- Locks and job metadata are correctness-critical.
- Cache eviction pressure should not silently delete coordination state.

Alternatives considered:
- Keep a single Redis with the same eviction policy for everything. Rejected because it is operationally unsafe for coordination data.

## Risks / Trade-offs

- [Migration complexity across many modules] -> Use plane-by-plane migration with unchanged API response contracts where possible and explicit async/result-lifecycle changes where necessary.
- [Short-term increase in spool storage usage] -> Enforce namespace TTLs, spool cleanup, and capacity telemetry before broad rollout.
- [Redis topology changes require ops coordination] -> Allow staged rollout via separate DB/index first, then separate instance if needed.
- [Some very small queries may become more operationally complex if forced into heavy-query path] -> Keep synchronous fast-path spool creation for small results, but still persist bodies only to Parquet.
- [Trace/lineage clients may depend on current Redis-body semantics] -> Preserve job/status/result endpoints while changing the backing storage to spool-backed result reconstruction.

## Migration Plan

1. Establish the architecture contract in specs and shared utilities.
2. Normalize snapshot-plane domains:
   - WIP remains the baseline.
   - resource master aligns to Redis snapshot semantics.
   - realtime equipment aligns to snapshot semantics without large worker-owned L1 payloads.
3. Normalize heavy-query runtime utilities:
   - shared DuckDB connection policy
   - shared spool metadata/index contract
   - shared async/result lifecycle semantics
4. Migrate trace/material/history domains that still store large Redis result bodies.
5. Decouple anomaly source seeding from derived-result computation.
6. Isolate Redis control-plane state from cache eviction pressure.

Rollback strategy:
- roll back domain by domain, not system-wide
- preserve spool metadata compatibility and canonical query identities during rollout
- maintain existing API response shape while toggling storage/runtime implementation behind the endpoints

## Open Questions

- Whether control-plane isolation should use separate Redis DBs first or jump directly to separate Redis instances.
- Whether small lookup indexes for snapshot-plane datasets should remain in Redis or be reconstructed on demand in request scope.
- Whether some query-tool endpoints should keep a lightweight Redis result cache for sub-second microqueries, or whether they should all converge on heavy-query spool behavior.
