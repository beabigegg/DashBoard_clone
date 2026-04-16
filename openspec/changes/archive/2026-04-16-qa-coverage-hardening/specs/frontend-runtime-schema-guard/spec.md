## ADDED Requirements

### Requirement: Frontend SHALL provide a shared unwrapApiResult utility
The system SHALL provide a single `frontend/src/core/unwrap-api-result.js` module consumed by all App.vue files, replacing the 10 duplicated inline definitions.

#### Scenario: Envelope success unwrap
- **WHEN** the API response is `{ success: true, data: <payload>, meta: {...} }`
- **THEN** `unwrapApiResult(response)` SHALL return `<payload>`

#### Scenario: Envelope error throws
- **WHEN** the API response is `{ success: false, error: { code, message }, meta: {...} }`
- **THEN** `unwrapApiResult(response)` SHALL throw an Error whose `message` equals the envelope message and whose `errorCode` equals `code`

#### Scenario: Legacy non-enveloped response
- **WHEN** the response lacks the `success` key but is a plain object
- **THEN** `unwrapApiResult(response)` SHALL return the response unchanged AND SHALL emit a `console.warn('[envelope-unknown] ...')` in DEV mode only

#### Scenario: Null or malformed response
- **WHEN** the response is `null`, `undefined`, or a primitive
- **THEN** `unwrapApiResult(response)` SHALL return a safe default (`{}`) without throwing

### Requirement: Frontend SHALL provide a runtime schema guard for high-risk endpoints
The system SHALL provide `frontend/src/core/schema-guard.js` with an `assertShape(value, spec)` utility and `frontend/src/core/endpoint-schemas.js` declaring expected data shapes for at least 5 high-risk endpoints.

#### Scenario: Known endpoint shape matches
- **WHEN** a response is received from `/api/hold-overview` and its `data` matches the declared schema
- **THEN** `guardResponse('hold-overview', payload)` SHALL return payload unchanged AND SHALL NOT emit any console warning

#### Scenario: Known endpoint shape mismatches in DEV
- **WHEN** the response to a guarded endpoint is missing a required field in DEV mode (`import.meta.env.DEV === true`)
- **THEN** `guardResponse(...)` SHALL emit `console.warn('[schema-guard] <endpoint>: <errors>')` AND SHALL return the payload unchanged (non-throwing)

#### Scenario: Production build strips DEV warnings
- **WHEN** the production bundle runs `guardResponse(...)`
- **THEN** no console warning SHALL be emitted even on shape mismatch
- **THEN** bundle size impact SHALL be less than 3KB gzipped for the guard layer

#### Scenario: Guarded endpoints coverage
- **WHEN** inspecting `endpoint-schemas.js`
- **THEN** it SHALL contain schemas for at least: `/api/hold-overview`, `/api/reject-history`, `/api/production-history`, `/api/material-trace`, `/api/analytics/anomaly-summary`

### Requirement: Frontend SHALL emit DEV-mode warnings for silent failure patterns
The system SHALL provide `frontend/src/core/dev-warnings.js` that detects and warns on five known silent-breakage categories.

#### Scenario: NaN pagination detection
- **WHEN** `Number(payload?.pagination?.page)` evaluates to `NaN` in DEV mode
- **THEN** a `[dev-warning:nan-pagination]` console warning SHALL be emitted once per endpoint

#### Scenario: Missing array element fields
- **WHEN** the first element of a guarded array lacks required fields per schema in DEV mode
- **THEN** a `[dev-warning:array-shape]` warning SHALL be emitted with the missing field names

#### Scenario: Spool download content-type mismatch
- **WHEN** a `spool_download_url` is fetched and the response `Content-Type` is not `application/octet-stream` or `application/vnd.apache.parquet`
- **THEN** a `[dev-warning:spool-content-type]` warning SHALL be emitted before attempting DuckDB parse

#### Scenario: Unknown response envelope
- **WHEN** `unwrapApiResult` falls into the legacy wildcard branch in DEV mode
- **THEN** a `[dev-warning:envelope-unknown]` warning SHALL be emitted with endpoint and keys

#### Scenario: Fetch called without AbortSignal
- **WHEN** a wrapped fetch call is invoked without a `signal` option in DEV mode
- **THEN** a `[dev-warning:missing-signal]` warning SHALL be emitted once per call site

### Requirement: Core API layer SHALL enforce fetch timeout and in-flight deduplication
`frontend/src/core/api.js` SHALL enforce a default fetch timeout and deduplicate in-flight identical requests.

#### Scenario: Default fetch timeout enforced
- **WHEN** an API call is made without explicit timeout
- **THEN** the request SHALL abort after 90 seconds and resolve with an Error whose `errorCode === 'FETCH_TIMEOUT'`

#### Scenario: In-flight request deduplication
- **WHEN** two identical requests (same method, URL, and body hash) are made while one is still pending
- **THEN** both callers SHALL receive the same Promise resolution
- **THEN** exactly one network request SHALL be sent

#### Scenario: Abort clears deduplication entry
- **WHEN** an AbortController aborts an in-flight request tracked in the dedup map
- **THEN** the dedup entry SHALL be removed so subsequent identical requests trigger a fresh fetch

### Requirement: Frontend SHALL track pending async jobs across page reloads
The system SHALL provide `frontend/src/core/pending-jobs-registry.js` that persists pending async job IDs to `localStorage` and recovers them on subsequent page loads.

#### Scenario: Pending job persistence
- **WHEN** an async query returns a 202 with `job_id`
- **THEN** the job_id and created_at SHALL be written to `localStorage` under a versioned key

#### Scenario: Pending job recovery on reload
- **WHEN** a page loads and finds non-expired pending jobs in `localStorage` for its endpoint
- **THEN** the composable SHALL offer to resume polling or discard the stale job

#### Scenario: Expired pending job cleanup
- **WHEN** a pending job entry older than 1800 seconds is encountered
- **THEN** it SHALL be removed from `localStorage` without action

### Requirement: Frontend SHALL detect application version drift via envelope meta
The system SHALL provide `frontend/src/core/app-version-check.js` that compares response `meta.app_version` to the loaded bundle version and surfaces an update banner on mismatch.

#### Scenario: Version match
- **WHEN** every response carries `meta.app_version` equal to the loaded bundle version
- **THEN** no banner SHALL be displayed

#### Scenario: Version mismatch on long-running page
- **WHEN** any response carries a newer `meta.app_version` than the loaded bundle
- **THEN** a persistent banner SHALL be displayed prompting the user to reload
- **THEN** the banner SHALL only appear once per session until reloaded
