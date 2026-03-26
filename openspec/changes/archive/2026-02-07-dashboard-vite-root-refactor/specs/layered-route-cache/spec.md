## ADDED Requirements

### Requirement: Route Cache SHALL Use Layered Storage
The route cache SHALL use L1 in-memory TTL cache and L2 Redis JSON cache when Redis is available.

#### Scenario: L1 cache hit
- **WHEN** a cached key exists in L1 and is unexpired
- **THEN** the API response SHALL be returned from memory without querying Redis

#### Scenario: L2 fallback
- **WHEN** a cached key is missing in L1 but exists in Redis
- **THEN** the value SHALL be returned and warmed into L1

### Requirement: Cache SHALL Degrade Gracefully Without Redis
The route cache SHALL remain functional with L1 cache when Redis is unavailable.

#### Scenario: Redis unavailable at startup
- **WHEN** Redis health check fails during app initialization
- **THEN** route cache operations SHALL continue using L1 cache without application failure
