## MODIFIED Requirements

### Requirement: Hold dataset cache SHALL handle cache expiry gracefully
The module SHALL return appropriate signals when cache has expired or the view engine cannot compute a result.

The hold-history domain is classified as **Type A** per the `query-response-semantic-contract`. On HTTP 410, the client SHALL re-trigger `execute_primary_query()` synchronously.

#### Scenario: Cache expired during view request
- **WHEN** `apply_view()` is called with a query_id whose spool file has expired
- **THEN** the response SHALL return `{ success: false, error: "cache_expired" }`
- **THEN** the HTTP status SHALL be 410 (Gone)

#### Scenario: Cache miss after transition from Redis to spool
- **WHEN** `apply_view()` is called with a query_id that has no spool metadata pointer and no Redis DataFrame key
- **THEN** the response SHALL return `{ success: false, error: "cache_expired" }` (treated as expired/miss)
- **THEN** the client SHALL re-trigger `execute_primary_query()`

#### Scenario: DuckDB runtime failure during view request
- **WHEN** `apply_view()` is called and the DuckDB SQL runtime returns no result (spool miss, runtime error, or feature flag disabled)
- **THEN** the response SHALL return `{ success: false, error: "cache_expired" }`
- **THEN** the HTTP status SHALL be 410 (Gone)
- **THEN** the system SHALL NOT call `_get_cached_df()` or `_derive_all_views()` pandas function

#### Scenario: Type A client re-triggers sync query on 410
- **WHEN** the hold-history view endpoint returns HTTP 410
- **THEN** the client SHALL call `execute_primary_query()` synchronously (no 202 / polling flow)
- **THEN** upon receiving a 200 response, the client SHALL load the view with the returned data
- **THEN** the view endpoint SHALL NOT dispatch any background job as a side-effect of the 410
