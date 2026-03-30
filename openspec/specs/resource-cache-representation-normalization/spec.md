# resource-cache-representation-normalization Specification

## Purpose
TBD - created by archiving change residual-hardening-round4. Update Purpose after archive.
## Requirements
### Requirement: Resource Derived Index MUST Avoid Full Record Duplication
The resource master snapshot SHALL not use a long-lived in-process full DataFrame plus a second long-lived derived index as the authoritative cache representation inside gunicorn workers. Any derived lookup structure SHALL be reconstructible from the canonical Redis snapshot and SHALL avoid retaining a second full resource payload copy in worker memory.

#### Scenario: Worker serves resource snapshot request
- **WHEN** a worker reads resource master data for a request
- **THEN** the canonical shared source SHALL be the Redis-backed resource snapshot
- **THEN** any request-scope lookup/index derived from that snapshot SHALL avoid a second full record copy in worker memory

#### Scenario: Build index from cached DataFrame
- **WHEN** resource cache data is parsed from Redis into process-level DataFrame
- **THEN** the derived index MUST store position-based references and metadata without a second full records copy

### Requirement: Resource Query APIs SHALL Preserve Existing Response Contract
Resource query APIs MUST keep existing output fields and semantics after index representation normalization.

#### Scenario: Read all resources after normalization
- **WHEN** callers request all resources or filtered resource lists
- **THEN** the returned payload MUST remain field-compatible with pre-normalization responses

### Requirement: Cache Invalidation MUST Keep Index/Data Coherent
The system SHALL invalidate and rebuild DataFrame/index representations atomically at cache refresh boundaries.

#### Scenario: Redis-backed cache refresh completes
- **WHEN** a new resource cache snapshot is published
- **THEN** stale index references MUST be invalidated before subsequent reads use refreshed DataFrame data

### Requirement: Resource cache Redis pipeline SHALL set TTL on data keys
The resource snapshot Redis retention window SHALL be aligned with the background sync interval and SHALL not expire before the next expected healthy refresh cycle.

#### Scenario: Normal updater write
- **WHEN** `resource_cache` publishes a new resource snapshot to Redis
- **THEN** all resource data and metadata keys SHALL receive a retention window that exceeds the configured resource sync interval
- **THEN** the retention window SHALL act as a stale-data safety valve instead of forcing predictable cache expiry during normal operation

#### Scenario: Updater healthy between sync cycles
- **WHEN** the resource updater is operating normally
- **THEN** the Redis snapshot SHALL remain available throughout the expected sync window
- **THEN** reads SHALL not predictably fall back to Oracle solely because Redis expired earlier than the next scheduled sync

#### Scenario: Updater stops for extended period
- **WHEN** no updater write occurs for more than 300 seconds
- **THEN** Redis data keys SHALL expire and be automatically removed
- **THEN** subsequent reads SHALL return cache miss (not stale data)

### Requirement: Equipment status cache Redis pipeline SHALL set TTL on data keys
The realtime equipment status snapshot SHALL follow the same snapshot-plane retention principle: Redis retention SHALL be aligned with the configured refresh cadence and workers SHALL not own the authoritative long-lived dataset copy.

#### Scenario: Equipment status snapshot refresh
- **WHEN** `realtime_equipment_cache` publishes a new equipment status snapshot
- **THEN** Redis SHALL remain the canonical shared payload store for the configured freshness window
- **THEN** long-lived worker-owned payload caches SHALL not become the authoritative dataset source

#### Scenario: Refresh cadence remains healthy
- **WHEN** the equipment status background refresh is running normally
- **THEN** Redis expiry SHALL not cause routine fallback behavior before the next expected refresh cycle

#### Scenario: Updater stops for extended period
- **WHEN** no updater write occurs for more than 300 seconds
- **THEN** Redis data keys SHALL expire and be automatically removed

