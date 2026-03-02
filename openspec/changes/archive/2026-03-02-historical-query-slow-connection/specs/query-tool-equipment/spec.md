## MODIFIED Requirements

### Requirement: Frontend API timeout
The query-tool equipment query, lot detail, lot jobs table, lot resolve, lot lineage, and reverse lineage composables SHALL use a 360-second API timeout for all Oracle-backed API calls.

#### Scenario: Equipment period query completes
- **WHEN** a user queries equipment history for a long period
- **THEN** the frontend does not abort the request for at least 360 seconds
