# Delta Spec: spool-warmup-scheduler

## ADDED Requirements

### Requirement: Spool seed failure logging severity

When `anomaly_detection_scheduler` spool seed fails due to `single_flight_timeout` (another worker already executing the same query), the system SHALL log at WARNING level, not ERROR.

All other spool seed failures SHALL remain at ERROR level.

#### Scenario: single_flight_timeout during multi-worker startup
- **WHEN** two gunicorn workers start simultaneously
- **AND** both attempt spool seed for the same dataset
- **AND** the second worker receives `single_flight_timeout`
- **THEN** the second worker logs at WARNING level with message indicating expected startup contention
- **AND** the function returns `False` (unchanged behavior)

#### Scenario: genuine Oracle query failure
- **WHEN** spool seed fails for a reason other than `single_flight_timeout` (e.g., ORA-12541, connection refused)
- **THEN** the failure is logged at ERROR level (unchanged behavior)
