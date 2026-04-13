## ADDED Requirements

### Requirement: Production History route validates required parameters before async enqueue
The `POST /api/production-history/query` endpoint SHALL validate `pj_types`, `start_date`, `end_date`, date ordering, and `MAX_DATE_RANGE_DAYS` range **before** enqueuing the request to the RQ worker. Invalid requests SHALL return HTTP 400 with a validation error envelope, not HTTP 202.

#### Scenario: Missing pj_types returns 400
- **WHEN** a POST request arrives with `start_date` and `end_date` but no `pj_types`
- **THEN** the route SHALL return HTTP 400 with error message `必要參數: pj_types（至少一個）` and SHALL NOT enqueue any async job

#### Scenario: Missing start_date returns 400
- **WHEN** a POST request arrives without `start_date`
- **THEN** the route SHALL return HTTP 400 with error message `必要參數: start_date, end_date` and SHALL NOT enqueue any async job

#### Scenario: Date range exceeds MAX_DATE_RANGE_DAYS returns 400
- **WHEN** a POST request arrives where `end_date - start_date + 1 > MAX_DATE_RANGE_DAYS` (730)
- **THEN** the route SHALL return HTTP 400 with error message indicating the limit and actual span, and SHALL NOT enqueue any async job

#### Scenario: Valid request proceeds to spool/async path
- **WHEN** a POST request arrives with all required parameters and a valid date range
- **THEN** the route SHALL continue with the existing spool-hit or async-enqueue flow unchanged

## MODIFIED Requirements

### Requirement: Production History route returns 202 for async queries
The `POST /api/production-history/query` endpoint SHALL return HTTP 202 with `{ async: true, job_id, status_url, dataset_id }` when **validated** query parameters are routed to the RQ worker. The endpoint SHALL validate parameters (see "Production History route validates required parameters before async enqueue") before any spool lookup or async enqueue decision.

#### Scenario: Spool hit returns 200 immediately
- **WHEN** a validated query request arrives and the spool/cache already has the result
- **THEN** the route SHALL return HTTP 200 with the full result (unchanged behavior)

#### Scenario: Spool miss with RQ available returns 202
- **WHEN** a validated query request arrives, spool misses, and `is_async_available()` returns True
- **THEN** the route SHALL enqueue the job and return HTTP 202 with `{ async: true, job_id, status_url }`

#### Scenario: Spool miss with RQ unavailable falls back to sync
- **WHEN** a validated query request arrives, spool misses, and `is_async_available()` returns False
- **THEN** the route SHALL execute the query synchronously (original behavior)

#### Scenario: Invalid parameters short-circuit to 400
- **WHEN** a query request arrives missing required parameters or with an out-of-range date span
- **THEN** the route SHALL return HTTP 400 **before** any spool lookup or enqueue attempt
