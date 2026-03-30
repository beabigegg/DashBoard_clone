## ADDED Requirements

### Requirement: Historical equipment queries SHALL use heavy-query storage when the result is replayable or large
Query-tool equipment history-style queries that are expensive, replayable, exportable, or expected to span broad date ranges SHALL use canonical heavy-query storage instead of Redis result payload caching.

#### Scenario: Large historical equipment-hours query
- **WHEN** an equipment history-style query spans a broad date range or produces a replayable result set
- **THEN** the system SHALL persist the canonical result body to heavy-query storage
- **THEN** Redis SHALL retain only metadata, lifecycle state, and lightweight indexes for that result

#### Scenario: Reuse of historical equipment result
- **WHEN** a subsequent request matches an existing canonical historical equipment query identity
- **THEN** the system SHALL reuse the canonical heavy-query result instead of rerunning Oracle or relying on a full Redis result payload
