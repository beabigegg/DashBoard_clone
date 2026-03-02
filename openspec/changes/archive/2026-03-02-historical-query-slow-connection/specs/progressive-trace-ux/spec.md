## MODIFIED Requirements

### Requirement: Trace stage timeout
The `useTraceProgress` composable's `DEFAULT_STAGE_TIMEOUT_MS` SHALL be 360000 (360 seconds) to accommodate large-scale trace operations.

#### Scenario: Large trace operation completes
- **WHEN** a trace stage (seed-resolve, lineage, or events) takes up to 300 seconds
- **THEN** the frontend does not abort the stage request
