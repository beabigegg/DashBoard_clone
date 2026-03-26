## ADDED Requirements

### Requirement: Process-Level Cache SHALL Use Bounded Capacity with Deterministic Eviction
Process-level parsed-data caches MUST enforce a configurable maximum key capacity and use deterministic eviction behavior when capacity is exceeded.

#### Scenario: Cache capacity reached
- **WHEN** a new cache entry is inserted and key capacity is at limit
- **THEN** cache MUST evict entries according to defined policy before storing the new key

#### Scenario: Repeated access updates recency
- **WHEN** an existing cache key is read or overwritten
- **THEN** eviction order MUST reflect recency semantics so hot keys are retained preferentially
