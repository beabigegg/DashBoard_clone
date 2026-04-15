## MODIFIED Requirements

### Requirement: Reject History API SHALL provide batch Pareto endpoint with cross-filter
The `/api/reject-history/batch-pareto` endpoint returns multi-dimension Pareto data from the spool cache.
This endpoint SHALL also accept `POST` with a JSON body carrying the same parameters, to avoid Gunicorn's 4094-byte request-line limit when many `reasons`, `workcenter_groups`, `trend_dates`, or `pareto_selections` values are selected.

#### Scenario: Batch pareto returns multi-dimension results
- **WHEN** `GET /api/reject-history/batch-pareto?query_id=<id>` is called
- **THEN** the response SHALL return `{ success: true, data: { dimensions: { reason: {...}, workcenter: {...}, package: {...} } } }`
- **THEN** each dimension SHALL include `items`, `dimension`, `metric_mode`

#### Scenario: Batch pareto POST avoids URL length limit
- **WHEN** `POST /api/reject-history/batch-pareto` is called with JSON body `{ "query_id": "<id>", "reasons": ["<reason1>", ..., "<reason30>"], "workcenter_groups": ["WC1","WC2"], "trend_dates": ["2024-01","2024-02",...] }`
- **THEN** the response SHALL return HTTP 200 with `{ success: true }`
- **THEN** the `compute_batch_pareto` service SHALL receive the same multi-value lists as the equivalent GET call

#### Scenario: Batch pareto POST reasons as JSON array
- **WHEN** `POST /api/reject-history/batch-pareto` is called with `reasons` as a JSON array `["A","B","C"]`
- **THEN** the filter SHALL be applied identically to `reasons=A,B,C` in GET

#### Scenario: Batch pareto missing query_id
- **WHEN** `GET /api/reject-history/batch-pareto` or `POST /api/reject-history/batch-pareto` is called without `query_id`
- **THEN** the response SHALL return HTTP 400 with `{ success: false, error: '缺少必要參數: query_id' }`

#### Scenario: Batch pareto cache miss
- **WHEN** the `query_id` is not found in spool cache
- **THEN** the response SHALL return `{ success: false, error_code: 'cache_miss' }` with HTTP 410

### Requirement: Reject History API SHALL expose view endpoint via POST
The `/api/reject-history/view` endpoint applies supplementary filters to a cached dataset.
This endpoint SHALL also accept `POST` with a JSON body carrying the same parameters.

#### Scenario: View returns filtered dataset from cache
- **WHEN** `GET /api/reject-history/view?query_id=<id>&page=1&per_page=50` is called
- **THEN** the response SHALL return the filtered, paginated view from the spool cache
- **THEN** on cache miss the response SHALL return HTTP 410 `cache_expired`

#### Scenario: View POST avoids URL length limit
- **WHEN** `POST /api/reject-history/view` is called with JSON body `{ "query_id": "<id>", "packages": ["P1","P2"], "workcenter_groups": ["WC1"], "reasons": ["<30 reasons>"], "trend_dates": ["2024-01",...], "page": 1, "per_page": 50 }`
- **THEN** the response SHALL return HTTP 200 with `{ success: true }`
- **THEN** `page` and `per_page` SHALL be correctly parsed as integers from the JSON body

#### Scenario: View POST native boolean params
- **WHEN** `POST /api/reject-history/view` is called with JSON body `{ "query_id": "<id>", "exclude_material_scrap": false, "exclude_pb_diode": true }`
- **THEN** `exclude_material_scrap` SHALL be treated as `false` (not coerced to `true` by string comparison)
- **THEN** `exclude_pb_diode` SHALL be treated as `true`

#### Scenario: View GET backward compatibility
- **WHEN** `GET /api/reject-history/view?query_id=<id>&packages=P1,P2&page=2` is called
- **THEN** the response SHALL return HTTP 200 unchanged from existing behavior
