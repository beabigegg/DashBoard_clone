## ADDED Requirements

### Requirement: The system SHALL classify cached and queryable data into four architecture planes
The system SHALL classify covered data flows into `snapshot`, `heavy-query`, `derived-result`, and `control` planes, and each covered module SHALL conform to the storage/runtime contract of its assigned plane.

#### Scenario: Snapshot-plane dataset
- **WHEN** a dataset is reused broadly across requests and refreshed on a background cadence
- **THEN** the dataset SHALL be assigned to the `snapshot` plane
- **THEN** Redis SHALL be the shared source of truth for the dataset payload
- **THEN** background refresh logic SHALL own freshness and publication of that dataset

#### Scenario: Heavy-query dataset
- **WHEN** a query result is historical, replayable, exportable, or expensive to recompute
- **THEN** the result SHALL be assigned to the `heavy-query` plane
- **THEN** the result body SHALL be stored as Parquet spool
- **THEN** DuckDB SHALL be the canonical runtime for page, view, and export operations over that result

#### Scenario: Derived-result dataset
- **WHEN** a dataset is computed from canonical source datasets and is materially smaller than the sources
- **THEN** the dataset SHALL be assigned to the `derived-result` plane
- **THEN** the derived payload MAY be stored in Redis
- **THEN** the derived layer SHALL not become the owner of source dataset warmup or freshness

#### Scenario: Control-plane state
- **WHEN** a key stores locks, inflight state, job status, progress, manifests, or lightweight metadata
- **THEN** that key SHALL be classified as `control`
- **THEN** it SHALL not share correctness assumptions with evictable cache payload storage

### Requirement: gunicorn web workers SHALL not retain large long-lived dataset bodies for covered planes
For modules covered by this architecture, gunicorn web workers SHALL not use long-lived in-process caches as the authoritative storage for large snapshot or heavy-query payloads.

#### Scenario: Snapshot-plane request handling
- **WHEN** a request reads snapshot-plane data
- **THEN** the request MAY materialize request-scope objects from Redis-backed storage
- **THEN** the worker SHALL not keep a long-lived full snapshot DataFrame or equivalent payload cache as the authoritative shared copy

#### Scenario: Heavy-query request handling
- **WHEN** a request reads heavy-query data
- **THEN** the request SHALL read from canonical spool-backed storage through DuckDB or equivalent spool-safe runtime
- **THEN** the worker SHALL not keep a long-lived full result payload cache in process memory

### Requirement: Redis data-plane and control-plane state SHALL be isolated from one another
The system SHALL isolate cache-payload storage from correctness-critical control-plane state so that eviction pressure on cached data does not invalidate locks, inflight state, or job metadata.

#### Scenario: Cache eviction pressure
- **WHEN** snapshot or heavy-query cache storage experiences memory pressure
- **THEN** control-plane keys for locks, inflight state, job status, and progress SHALL remain protected from the same eviction policy

#### Scenario: Deployment topology
- **WHEN** the system is configured for production use
- **THEN** Redis topology SHALL provide separate control-plane and data-plane eviction behavior, whether by separate DBs or separate Redis instances
