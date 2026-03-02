## MODIFIED Requirements

### Requirement: Frontend API timeout
The hold-history page SHALL use a 360-second API timeout (up from 60 seconds) for all Oracle-backed API calls.

#### Scenario: Large date range query completes
- **WHEN** a user queries hold history for a long date range
- **THEN** the frontend does not abort the request for at least 360 seconds
