# resource-cache-representation-normalization Specification

## Purpose
TBD - created by archiving change residual-hardening-round4. Update Purpose after archive.
## Requirements
### Requirement: Resource Derived Index MUST Avoid Full Record Duplication
Resource derived index SHALL use lightweight row-position references instead of storing full duplicated record payloads alongside the process DataFrame cache.

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
The `resource_cache.py` Redis pipeline write SHALL include an expiry of 300 seconds on all data keys.

#### Scenario: Normal updater write
- **WHEN** `resource_cache` writes a new snapshot to Redis via pipeline
- **THEN** all data keys (`data`, `meta:*`) SHALL have TTL set to 300 seconds (EX 300)

#### Scenario: Updater runs within TTL window
- **WHEN** the updater sync interval (30-60s) completes before TTL expires
- **THEN** the TTL SHALL be refreshed on each write, preventing expiry during normal operation

#### Scenario: Updater stops for extended period
- **WHEN** no updater write occurs for more than 300 seconds
- **THEN** Redis data keys SHALL expire and be automatically removed
- **THEN** subsequent reads SHALL return cache miss (not stale data)

### Requirement: Equipment status cache Redis pipeline SHALL set TTL on data keys
The `realtime_equipment_cache.py` Redis pipeline write SHALL include an expiry of 300 seconds on all data keys.

#### Scenario: Normal updater write
- **WHEN** `realtime_equipment_cache` writes a new snapshot to Redis via pipeline
- **THEN** all data keys SHALL have TTL set to 300 seconds (EX 300)

#### Scenario: Updater stops for extended period
- **WHEN** no updater write occurs for more than 300 seconds
- **THEN** Redis data keys SHALL expire and be automatically removed

