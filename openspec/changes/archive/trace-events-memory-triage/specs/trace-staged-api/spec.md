## MODIFIED Requirements

### Requirement: Trace events endpoint SHALL manage memory for large queries
The events endpoint SHALL proactively release memory after processing large CID sets.

#### Scenario: Admission control for non-MSD profiles
- **WHEN** the events endpoint receives a non-MSD profile request with `container_ids` count exceeding `TRACE_EVENTS_CID_LIMIT` (env: `TRACE_EVENTS_CID_LIMIT`, default: 50000)
- **THEN** the endpoint SHALL return HTTP 413 with `{ "error": "...", "code": "CID_LIMIT_EXCEEDED", "cid_count": N, "limit": M }`
- **THEN** Oracle DB connection pool SHALL NOT be consumed

#### Scenario: MSD profile bypasses CID hard limit
- **WHEN** the events endpoint receives a `mid_section_defect` profile request regardless of CID count
- **THEN** the endpoint SHALL proceed with normal processing (no CID hard limit)
- **THEN** if CID count exceeds 50000, the endpoint SHALL log a warning with `cid_count` for monitoring

#### Scenario: Non-MSD profile avoids double memory retention
- **WHEN** a non-MSD events request completes domain fetching
- **THEN** the `events_by_cid` reference SHALL be deleted immediately after `_flatten_domain_records`
- **THEN** only the flattened `results` dict SHALL remain in memory
