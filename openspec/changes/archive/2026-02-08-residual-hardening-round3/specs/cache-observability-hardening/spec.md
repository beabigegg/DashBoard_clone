## ADDED Requirements

### Requirement: Cache Publish MUST Preserve Previous Readable Snapshot on Failure
When refreshing full-table cache payloads, the system MUST avoid exposing partially published states to readers.

#### Scenario: Publish fails after payload serialization
- **WHEN** a cache refresh has prepared new payload but publish operation fails
- **THEN** previously published cache keys MUST remain readable and metadata MUST remain consistent with old snapshot

#### Scenario: Publish succeeds
- **WHEN** publish operation completes successfully
- **THEN** data payload and metadata keys MUST be visible as one coherent new snapshot

### Requirement: Process-Level Cache Slow Path SHALL Minimize Lock Hold Time
Large payload parsing MUST NOT happen inside long-held process cache locks.

#### Scenario: Cache miss under concurrent requests
- **WHEN** multiple requests hit process cache miss
- **THEN** parsing work SHALL happen outside lock-protected mutation section, and lock scope SHALL be limited to consistency check + commit

### Requirement: Process-Level Cache Policies MUST Stay Consistent Across Services
All service-local process caches MUST support bounded capacity with deterministic eviction.

#### Scenario: Realtime equipment cache growth
- **WHEN** realtime equipment process cache reaches configured capacity
- **THEN** entries MUST be evicted according to deterministic LRU behavior
