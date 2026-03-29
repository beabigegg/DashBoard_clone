## ADDED Requirements

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
