## Purpose
Define stable requirements for cache-observability-hardening.
## Requirements
### Requirement: Layered Cache SHALL Expose Operational State
The route cache implementation SHALL expose layered cache operational state, including mode, freshness, and degradation status.

#### Scenario: Redis unavailable degradation state
- **WHEN** Redis is unavailable
- **THEN** health endpoints MUST indicate degraded cache mode while keeping L1 memory cache active

### Requirement: Cache Telemetry MUST be Queryable for Operations
The system MUST provide cache telemetry suitable for operations diagnostics.

#### Scenario: Telemetry inspection
- **WHEN** operators request deep health status
- **THEN** cache-related metrics/state SHALL be present and interpretable for troubleshooting

### Requirement: Health Endpoints SHALL Expose Pool Saturation and Degradation Reason Codes
Operational health endpoints MUST report connection pool saturation indicators and explicit degradation reason codes.

#### Scenario: Pool saturation observed
- **WHEN** checked-out connections and overflow approach configured limits
- **THEN** deep health output MUST expose saturation metrics and degraded reason classification

### Requirement: Degraded Responses MUST Be Correlatable Across API and Health Telemetry
Error responses for degraded states SHALL include stable codes that can be mapped to health telemetry and operational dashboards.

#### Scenario: Degraded API response correlation
- **WHEN** an API request fails due to circuit-open or pool-exhausted conditions
- **THEN** operators MUST be able to match the response code to current health telemetry state

### Requirement: Operational Alert Thresholds SHALL Be Explicitly Defined
The system MUST define alert thresholds for sustained degraded state, repeated worker recovery, and abnormal retry pressure.

#### Scenario: Sustained degradation threshold exceeded
- **WHEN** degraded status persists beyond configured duration
- **THEN** the monitoring contract MUST classify the service as alert-worthy with actionable context

### Requirement: Cache Telemetry SHALL Include Memory Amplification Signals
Operational telemetry MUST expose cache-domain memory usage indicators and representation amplification factors, and MUST differentiate between authoritative data payload and derived/index helper structures.

#### Scenario: Deep health telemetry request after representation normalization
- **WHEN** operators inspect cache telemetry for resource or WIP domains
- **THEN** telemetry MUST include per-domain memory footprint, amplification indicators, and enough structure detail to verify that full-record duplication is not reintroduced

### Requirement: Efficiency Benchmarks SHALL Gate Cache Refactor Rollout
Cache/query efficiency changes MUST be validated against baseline latency and memory benchmarks before rollout.

#### Scenario: Pre-release validation
- **WHEN** cache refactor changes are prepared for deployment
- **THEN** benchmark results MUST demonstrate no regression beyond configured thresholds for P95 latency and memory usage

### Requirement: Process-Level Cache SHALL Use Bounded Capacity with Deterministic Eviction
Process-level parsed-data caches MUST enforce a configurable maximum key capacity and use deterministic eviction behavior when capacity is exceeded.

#### Scenario: Cache capacity reached
- **WHEN** a new cache entry is inserted and key capacity is at limit
- **THEN** cache MUST evict entries according to defined policy before storing the new key

#### Scenario: Repeated access updates recency
- **WHEN** an existing cache key is read or overwritten
- **THEN** eviction order MUST reflect recency semantics so hot keys are retained preferentially

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

