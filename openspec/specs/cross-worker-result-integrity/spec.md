# cross-worker-result-integrity Specification

## Purpose
TBD - created by archiving change qa-coverage-hardening. Update Purpose after archive.
## Requirements
### Requirement: Async query results SHALL be retrievable from any gunicorn worker
Results produced on one gunicorn/RQ worker SHALL be accessible from any other worker handling subsequent polls or reads.

#### Scenario: Job submitted on worker A retrieved from worker B
- **WHEN** a client submits an async query routed to gunicorn worker A and subsequently polls the status routed to worker B
- **THEN** worker B SHALL return the job's current state from shared Redis without `NOT_FOUND`

#### Scenario: Grace retry for transient not-found
- **WHEN** a poll reaches a worker before Redis has propagated the initial job registration (< 500ms window)
- **THEN** the `useAsyncJobPolling` composable SHALL retry up to 3 times with 300ms backoff before surfacing an error

### Requirement: Spool directory SHALL be a shared volume validated at startup
`QUERY_SPOOL_DIR` SHALL reside on a filesystem that is writable from all worker processes and validated at application startup.

#### Scenario: Startup validation passes
- **WHEN** the application starts and `QUERY_SPOOL_DIR` is on a shared volume accessible by all workers
- **THEN** startup SHALL proceed without warning

#### Scenario: Startup validation warns on process-local path
- **WHEN** `QUERY_SPOOL_DIR` resolves to a process-local path (e.g. `/tmp` in a containerised deployment without bind mount)
- **THEN** a startup WARNING log SHALL be emitted identifying the cross-worker-sharing risk

### Requirement: Spool writes SHALL be atomic via tmp-then-rename
All parquet files produced into the spool SHALL be written to a temporary path and atomically renamed to their final location.

#### Scenario: Reader during concurrent write
- **WHEN** a reader accesses a spool file while a writer is producing a newer version of the same query_id
- **THEN** the reader SHALL either see the complete old file or the complete new file, never a partially written file

#### Scenario: Writer crash leaves no partial file
- **WHEN** a writer process is killed mid-write
- **THEN** only the temporary file SHALL exist AND the final path SHALL be unchanged AND cleanup SHALL reclaim the orphan temp file within the grace period

### Requirement: Cache refill across workers SHALL be protected by a distributed lock
Cache refill for identical query fingerprints SHALL be serialised across gunicorn workers using a Redis-based lock.

#### Scenario: Two workers refill same key
- **WHEN** two workers attempt to refill the same cache key simultaneously
- **THEN** exactly one worker SHALL execute the upstream query
- **THEN** the other worker SHALL wait (bounded) and read the refilled cache value

#### Scenario: Lock auto-releases on holder crash
- **WHEN** the lock holder crashes before releasing
- **THEN** the lock SHALL expire within its configured TTL (at least p95 query time plus safety margin)
- **THEN** a subsequent contender SHALL acquire the lock and proceed

#### Scenario: Thundering herd single refill
- **WHEN** N concurrent requests hit the same missing cache entry
- **THEN** at most one upstream Oracle query SHALL be executed
- **THEN** all N requests SHALL return equivalent data

### Requirement: Serialisation round-trips SHALL preserve datatypes across workers
Values written to the spool or Redis on one worker SHALL be readable with equivalent types on another.

#### Scenario: Timestamp round-trip
- **WHEN** a `datetime` value is written as a parquet/JSON field and read back on a different worker
- **THEN** the resulting value SHALL compare equal in ISO-8601 UTC string form

#### Scenario: NaN/Null preservation
- **WHEN** numeric NaN or SQL NULL values are written and read back
- **THEN** the reader SHALL observe the same null semantics without coercion to 0 or empty string

#### Scenario: Unicode preservation
- **WHEN** strings containing full-width CJK, emoji, or quoted characters are written and read back
- **THEN** the reader SHALL observe the exact same byte sequence

### Requirement: Process-level caches SHALL be marked and scoped
`_ProcessLevelCache` instances (currently in `resource_cache.py` and `realtime_equipment_cache.py`) SHALL be explicitly documented as single-worker and SHALL NOT be relied on by any cross-worker flow.

#### Scenario: Cross-worker flow forbids process cache
- **WHEN** a static check inspects `_ProcessLevelCache` usages
- **THEN** each usage SHALL have a documented fallback to Redis or equivalent shared storage
- **THEN** no async job result SHALL depend solely on `_ProcessLevelCache` for cross-request retrieval

