## ADDED Requirements

### Requirement: Reason filter cache service
The system SHALL provide a `reason_filter_cache` service that caches LOSSREASONNAME values from `DWH.DW_MES_LOTREJECTHISTORY` (limited to last 365 days) with L1 memory + L2 Redis and a 24-hour TTL.

#### Scenario: Cache initialization at startup
- **WHEN** the application starts
- **THEN** `reason_filter_cache.init()` SHALL query `SELECT DISTINCT TRIM(LOSSREASONNAME) FROM DW_MES_LOTREJECTHISTORY WHERE TXNDATE >= SYSDATE - 365 AND LOSSREASONNAME IS NOT NULL`
- **AND** results SHALL be stored in L1 and L2 with a 24-hour TTL
- **AND** the query SHALL use the main pool

#### Scenario: Cache provides reject reasons
- **WHEN** `get_reject_reasons()` is called
- **THEN** it SHALL return the cached list of distinct LOSSREASONNAME values
- **AND** response time SHALL be under 10ms

#### Scenario: Cache refresh with fail-open
- **WHEN** the 24-hour cache refresh fails (Oracle error)
- **THEN** the previous cached values SHALL be retained
- **AND** a warning SHALL be logged

### Requirement: Reject history uses reason filter cache
`reject_history_service.get_filter_options()` SHALL read reasons from `reason_filter_cache.get_reject_reasons()` instead of running the full base CTE query.

#### Scenario: Filter options returns cached reasons
- **WHEN** `get_filter_options()` is called
- **THEN** the reasons list SHALL come from `reason_filter_cache.get_reject_reasons()`
- **AND** the response time SHALL be under 100ms (previously 5.85s)

### Requirement: Mid-section defect uses reason filter cache
`mid_section_defect_service` SHALL use `reason_filter_cache` for its available loss reasons dropdown, eliminating slow-path Oracle queries for this purpose.

#### Scenario: Loss reasons from cache
- **WHEN** the mid-section defect analysis needs available loss reasons for the filter dropdown
- **THEN** it SHALL read from `reason_filter_cache.get_reject_reasons()`
- **AND** it SHALL NOT occupy a slow pool connection for this purpose
