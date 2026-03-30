## MODIFIED Requirements

### Requirement: Resource Derived Index MUST Avoid Full Record Duplication
The resource master snapshot SHALL not use a long-lived in-process full DataFrame plus a second long-lived derived index as the authoritative cache representation inside gunicorn workers. Any derived lookup structure SHALL be reconstructible from the canonical Redis snapshot and SHALL avoid retaining a second full resource payload copy in worker memory.

#### Scenario: Worker serves resource snapshot request
- **WHEN** a worker reads resource master data for a request
- **THEN** the canonical shared source SHALL be the Redis-backed resource snapshot
- **THEN** any request-scope lookup/index derived from that snapshot SHALL avoid a second full record copy in worker memory

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

### Requirement: Equipment status cache Redis pipeline SHALL set TTL on data keys
The realtime equipment status snapshot SHALL follow the same snapshot-plane retention principle: Redis retention SHALL be aligned with the configured refresh cadence and workers SHALL not own the authoritative long-lived dataset copy.

#### Scenario: Equipment status snapshot refresh
- **WHEN** `realtime_equipment_cache` publishes a new equipment status snapshot
- **THEN** Redis SHALL remain the canonical shared payload store for the configured freshness window
- **THEN** long-lived worker-owned payload caches SHALL not become the authoritative dataset source

#### Scenario: Refresh cadence remains healthy
- **WHEN** the equipment status background refresh is running normally
- **THEN** Redis expiry SHALL not cause routine fallback behavior before the next expected refresh cycle
