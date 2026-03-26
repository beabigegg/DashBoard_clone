## ADDED Requirements

### Requirement: Trace events endpoint SHALL limit domain concurrency
The `/api/trace/events` endpoint SHALL use `TRACE_EVENTS_MAX_WORKERS` to control how many domains execute concurrently.

#### Scenario: Default domain concurrency
- **WHEN** the events endpoint dispatches domain queries
- **THEN** the default `TRACE_EVENTS_MAX_WORKERS` SHALL be 2 (env: `TRACE_EVENTS_MAX_WORKERS`)

### Requirement: Trace events endpoint SHALL manage memory for large queries
The events endpoint SHALL proactively release memory after processing large CID sets.

#### Scenario: Early release of grouped domain results
- **WHEN** MSD aggregation completes using `raw_domain_results`
- **THEN** the `raw_domain_results` reference SHALL be deleted immediately after aggregation
- **THEN** for non-MSD profiles, `raw_domain_results` SHALL be deleted after result assembly

#### Scenario: Garbage collection for large CID sets
- **WHEN** the events endpoint completes processing and the CID count exceeds 10000
- **THEN** `gc.collect()` SHALL be called to prompt Python garbage collection

#### Scenario: Large CID set skips route-level cache
- **WHEN** the events endpoint completes for a non-MSD profile and CID count exceeds 10000
- **THEN** the route-level events cache write SHALL be skipped
