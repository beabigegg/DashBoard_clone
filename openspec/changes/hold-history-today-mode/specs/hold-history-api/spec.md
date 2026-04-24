## MODIFIED Requirements

### Requirement: Hold History API SHALL provide daily trend data with Redis caching

The Hold History API SHALL return trend, reason-pareto, duration, and list data from a single cached dataset via a two-phase query pattern (POST /query + GET /view). The Record Type filter parameter is NO LONGER exposed in range-mode UI; the backend SHALL continue to accept the parameter for API backward compatibility but the range-mode page SHALL always omit it (equivalent to `record_type=new`).

#### Scenario: Primary query endpoint

- **WHEN** `POST /api/hold-history/query` is called with `{ start_date, end_date, hold_type }`
- **THEN** the service SHALL execute a single Oracle query (or read from cache) via `hold_dataset_cache.execute_primary_query()`
- **THEN** the response SHALL return `{ success: true, data: { query_id, trend, reason_pareto, duration, list, summary } }`
- **THEN** list SHALL contain page 1 with default per_page of 50
- **AND** the `record_type` parameter SHALL still be accepted when provided (for API clients), defaulting to `new` when omitted

#### Scenario: Supplementary view endpoint

- **WHEN** `GET /api/hold-history/view?query_id=...&hold_type=...&reason=...&page=...&per_page=...` is called
- **THEN** the service SHALL read the cached DataFrame and derive filtered views via `hold_dataset_cache.apply_view()`
- **THEN** no Oracle query SHALL be executed
- **THEN** the response SHALL return `{ success: true, data: { trend, reason_pareto, duration, list } }`
- **AND** the `record_type` parameter SHALL still be accepted when provided, defaulting to `new` when omitted

#### Scenario: Cache expired on view request

- **WHEN** GET /view is called with an expired query_id
- **THEN** the response SHALL return `{ success: false, error: "cache_expired" }` with HTTP 410

#### Scenario: Trend uses shift boundary at 07:30

- **WHEN** daily aggregation is calculated
- **THEN** transactions with time >= 07:30 SHALL be attributed to the next calendar day
- **THEN** transactions with time < 07:30 SHALL be attributed to the current calendar day

#### Scenario: Trend hold type classification

- **WHEN** trend data is aggregated by hold type
- **THEN** quality classification SHALL use the same NON_QUALITY_HOLD_REASONS set as existing hold endpoints
