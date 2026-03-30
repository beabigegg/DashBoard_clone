## MODIFIED Requirements

### Requirement: Material trace SHALL migrate to spool-backed execution
Material trace query and export SHALL use canonical heavy-query storage: the reusable result body SHALL live in Parquet spool and all pagination, replay, and export behavior SHALL read from the canonical spool-backed result.

#### Scenario: Spool hit
- **WHEN** a material trace request matches a valid canonical spool-backed result
- **THEN** the route SHALL return paginated/query results from the spool-backed runtime without rerunning Oracle work

#### Scenario: Spool miss
- **WHEN** no canonical spool-backed result exists for the request
- **THEN** the system SHALL create one through the heavy-query execution path before the result becomes reusable
- **THEN** Redis SHALL not become the canonical body store for that result

#### Scenario: Export from canonical result
- **WHEN** a client exports material trace results
- **THEN** the export SHALL read from the same canonical spool-backed result identity used by query pagination and replay
- **THEN** export behavior SHALL not require a separate full-result Redis or in-memory body cache
