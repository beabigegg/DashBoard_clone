## Purpose
Define stable requirements for hold-overview-api.

## Requirements


### Requirement: Hold Overview API SHALL provide summary statistics
The API SHALL return aggregated summary KPIs for hold lots.
`GET /api/hold-overview/summary` SHALL also accept `POST` with a JSON body carrying the same parameters, to avoid Gunicorn's 4094-byte request-line limit when many filter values are selected.

#### Scenario: Summary endpoint delegates to extended get_hold_detail_summary
- **WHEN** `GET /api/hold-overview/summary` is called with `hold_type=quality`
- **THEN** the route SHALL delegate to the extended `get_hold_detail_summary(reason=None, hold_type='quality')`
- **THEN** the response SHALL return `{ success: true, data: { totalLots, totalQty, workcenterCount, avgAge, maxAge, dataUpdateDate } }`
- **THEN** only lots with EQUIPMENTCOUNT=0 AND CURRENTHOLDCOUNT>0 SHALL be included
- **THEN** hold_type classification SHALL use the same NON_QUALITY_HOLD_REASONS set as existing hold endpoints

#### Scenario: Summary with reason filter
- **WHEN** `GET /api/hold-overview/summary?hold_type=quality&reason=品質確認` is called
- **THEN** the response SHALL only include lots where HOLDREASONNAME equals the specified reason

#### Scenario: Summary hold_type=all
- **WHEN** `GET /api/hold-overview/summary?hold_type=all` is called
- **THEN** the response SHALL include both quality and non-quality hold lots

#### Scenario: Summary error
- **WHEN** the database query fails
- **THEN** the response SHALL return `{ success: false, error: '查詢失敗' }` with HTTP 500

#### Scenario: Summary via POST avoids URL length limit
- **WHEN** `POST /api/hold-overview/summary` is called with JSON body `{ "lotid": "<60+ comma-separated lot IDs>", "hold_type": "quality" }`
- **THEN** the response SHALL return HTTP 200 with `{ success: true }`
- **THEN** the service layer SHALL receive the same parameters as the equivalent GET request

#### Scenario: Summary POST reason as JSON array
- **WHEN** `POST /api/hold-overview/summary` is called with JSON body `{ "reason": ["品質確認", "YieldLimit"] }`
- **THEN** the reason filter SHALL be applied as if `reason=品質確認,YieldLimit` was given in GET

### Requirement: Hold Overview API SHALL provide workcenter x package matrix
The API SHALL return a cross-tabulation of workcenters and packages for hold lots.
`GET /api/hold-overview/matrix` SHALL also accept `POST` with a JSON body.

#### Scenario: Matrix endpoint
- **WHEN** `GET /api/hold-overview/matrix` is called with `hold_type=quality`
- **THEN** the response SHALL return the same matrix structure as `/api/wip/overview/matrix`: `{ workcenters, packages, matrix, workcenter_totals, package_totals, grand_total }`
- **THEN** workcenters SHALL be sorted by WORKCENTERSEQUENCE_GROUP
- **THEN** packages SHALL be sorted by total QTY descending
- **THEN** only HOLD status lots matching the hold_type SHALL be included

#### Scenario: Matrix delegates to existing get_wip_matrix
- **WHEN** the matrix endpoint is called
- **THEN** it SHALL delegate to `get_wip_matrix(status='HOLD', hold_type=...)` from wip_service.py

#### Scenario: Matrix with reason filter
- **WHEN** `GET /api/hold-overview/matrix?hold_type=quality&reason=品質確認` is called
- **THEN** the matrix SHALL only include lots where HOLDREASONNAME equals the specified reason

#### Scenario: Matrix via POST avoids URL length limit
- **WHEN** `POST /api/hold-overview/matrix` is called with JSON body `{ "lotid": "<60+ lot IDs>", "hold_type": "all" }`
- **THEN** the response SHALL return HTTP 200 with `{ success: true }`

### Requirement: Hold Overview API SHALL provide TreeMap aggregation data
The API SHALL return aggregated data suitable for TreeMap visualization.
`GET /api/hold-overview/treemap` SHALL also accept `POST` with a JSON body.

#### Scenario: TreeMap endpoint uses new get_hold_overview_treemap function
- **WHEN** `GET /api/hold-overview/treemap` is called with `hold_type=quality`
- **THEN** the route SHALL delegate to `get_hold_overview_treemap()` (the only new service function)
- **THEN** the response SHALL return `{ success: true, data: { items: [...] } }`
- **THEN** each item SHALL contain `{ workcenter, reason, lots, qty, avgAge }`
- **THEN** items SHALL be grouped by (WORKCENTER_GROUP, HOLDREASONNAME)
- **THEN** avgAge SHALL be calculated using the pre-computed AGEBYDAYS column from DW_MES_LOT_V

#### Scenario: TreeMap with matrix filter
- **WHEN** `GET /api/hold-overview/treemap?hold_type=quality&workcenter=WC-MOLD&package=PKG-A` is called
- **THEN** the response SHALL only include lots matching the workcenter AND package filters

#### Scenario: TreeMap with reason filter
- **WHEN** `GET /api/hold-overview/treemap?hold_type=quality&reason=品質確認` is called
- **THEN** the response SHALL only include lots where HOLDREASONNAME equals the specified reason

#### Scenario: TreeMap empty result
- **WHEN** no hold lots match the filters
- **THEN** the response SHALL return `{ success: true, data: { items: [] } }`

#### Scenario: TreeMap via POST
- **WHEN** `POST /api/hold-overview/treemap` is called with JSON body `{ "reason": ["品質確認", "YieldLimit"], "hold_type": "all" }`
- **THEN** the response SHALL return HTTP 200 with `{ success: true }`

### Requirement: Hold Overview API SHALL provide paginated lot details
The API SHALL return a paginated list of hold lot details.
`GET /api/hold-overview/lots` SHALL also accept `POST` with a JSON body.

#### Scenario: Lots endpoint delegates to extended get_hold_detail_lots
- **WHEN** `GET /api/hold-overview/lots?hold_type=quality&page=1&per_page=50` is called
- **THEN** the route SHALL delegate to the extended `get_hold_detail_lots(reason=None, hold_type='quality', ...)`
- **THEN** the response SHALL return `{ success: true, data: { lots: [...], pagination: { page, perPage, total, totalPages } } }`
- **THEN** each lot SHALL contain: lotId, workorder, qty, package, workcenter, holdReason, age, holdBy, dept, holdComment
- **THEN** lots SHALL be sorted by age descending (longest hold first)

#### Scenario: Lots via POST with pagination
- **WHEN** `POST /api/hold-overview/lots` is called with JSON body `{ "lotid": "<60+ lot IDs>", "hold_type": "quality", "page": 2, "per_page": 20 }`
- **THEN** the response SHALL return HTTP 200 with `{ success: true }`
- **THEN** `page` and `per_page` SHALL be correctly parsed as integers from the JSON body

#### Scenario: Lots with matrix filter
- **WHEN** `GET /api/hold-overview/lots?hold_type=quality&workcenter=WC-MOLD&package=PKG-A` is called
- **THEN** only lots matching the workcenter AND package filters SHALL be returned

#### Scenario: Lots with treemap filter
- **WHEN** `GET /api/hold-overview/lots?hold_type=quality&workcenter=WC-MOLD&treemap_reason=品質確認` is called
- **THEN** only lots matching the workcenter AND treemap_reason SHALL be returned

#### Scenario: Lots with all filters combined
- **WHEN** `GET /api/hold-overview/lots?hold_type=quality&reason=品質確認&workcenter=WC-MOLD&package=PKG-A&treemap_reason=品質確認` is called
- **THEN** all filters SHALL be applied as AND conditions

#### Scenario: Lots pagination bounds
- **WHEN** `page` is less than 1
- **THEN** page SHALL be treated as 1
- **WHEN** `per_page` exceeds 200
- **THEN** per_page SHALL be capped at 200

#### Scenario: Lots error
- **WHEN** the database query fails
- **THEN** the response SHALL return `{ success: false, error: '查詢失敗' }` with HTTP 500

### Requirement: Hold Overview API SHALL apply rate limiting
The API SHALL apply rate limiting to expensive endpoints.

#### Scenario: Rate limit on lots endpoint
- **WHEN** the lots endpoint receives excessive requests
- **THEN** rate limiting SHALL be applied using `configured_rate_limit` with a default of 90 requests per 60 seconds

#### Scenario: Rate limit on matrix endpoint
- **WHEN** the matrix endpoint receives excessive requests
- **THEN** rate limiting SHALL be applied using `configured_rate_limit` with a default of 120 requests per 60 seconds

### Requirement: Hold Overview page route SHALL serve static Vite HTML
The Flask route SHALL serve the pre-built Vite HTML file.

#### Scenario: Page route
- **WHEN** user navigates to `/hold-overview`
- **THEN** Flask SHALL serve the pre-built HTML file from `static/dist/hold-overview.html` via `send_from_directory`
- **THEN** the HTML SHALL NOT pass through Jinja2 template rendering

#### Scenario: Fallback HTML
- **WHEN** the pre-built HTML file does not exist
- **THEN** Flask SHALL return a minimal HTML page with the correct script tag and module import

### Requirement: Extended service functions SHALL maintain backward compatibility
The extended `get_hold_detail_summary()`, `get_hold_detail_lots()`, and `get_wip_matrix()` SHALL not break existing callers.

#### Scenario: Hold Detail summary backward compatibility
- **WHEN** existing Hold Detail code calls `get_hold_detail_summary(reason='xxx')`
- **THEN** the result SHALL be identical to the pre-extension behavior
- **THEN** the new `hold_type` parameter SHALL default to None (no additional filtering)

#### Scenario: Hold Detail lots backward compatibility
- **WHEN** existing Hold Detail code calls `get_hold_detail_lots(reason='xxx', workcenter=..., package=..., age_range=...)`
- **THEN** the result SHALL be identical to the pre-extension behavior
- **THEN** the new `hold_type` and `treemap_reason` parameters SHALL default to None

#### Scenario: WIP Overview matrix backward compatibility
- **WHEN** existing WIP Overview code calls `get_wip_matrix(status='HOLD', hold_type='quality')`
- **THEN** the result SHALL be identical to the pre-extension behavior
- **THEN** the new `reason` parameter SHALL default to None (no HOLDREASONNAME filtering)

### Requirement: Hold Overview API SHALL accept lotid and workorder as exact-match filters
Hold Overview API endpoints (`/api/hold-overview/summary`, `/api/hold-overview/matrix`, `/api/hold-overview/lots`) SHALL document and implement `lotid` and `workorder` parameters as **exact match** (case-insensitive), not fuzzy/substring match.

#### Scenario: Summary with lotid exact filter
- **WHEN** `GET /api/hold-overview/summary?lotid=A100,B200` is called
- **THEN** the response SHALL only include hold lots where `LOTID` exactly equals `A100` or `B200`
- **THEN** lots where `LOTID` merely contains `A100` as a substring SHALL NOT be included

#### Scenario: Summary via POST avoids URL length limit
- **WHEN** `POST /api/hold-overview/summary` is called with JSON body `{ "lotid": "<60+ comma-separated lot IDs>", "hold_type": "quality" }`
- **THEN** the response SHALL return HTTP 200 with `{ success: true }`
- **THEN** the service layer SHALL receive the same parameters as the equivalent GET request
- **THEN** filtering SHALL use exact match semantics

#### Scenario: Summary POST reason as JSON array
- **WHEN** `POST /api/hold-overview/summary` is called with JSON body `{ "reason": ["品質確認", "YieldLimit"] }`
- **THEN** the reason filter SHALL be applied as if `reason=品質確認,YieldLimit` was given in GET

### Requirement: Hold Overview API SHALL accept `/api/wip/overview/hold` via POST
`GET /api/wip/overview/hold` SHALL also accept `POST` with a JSON body carrying the same filter parameters.

#### Scenario: WIP hold endpoint POST avoids URL length limit
- **WHEN** `POST /api/wip/overview/hold` is called with JSON body containing 60+ comma-separated lot IDs in `lotid`
- **THEN** the response SHALL return HTTP 200 with `{ success: true }`
- **THEN** the service SHALL receive the same `lotid` string as the equivalent GET call

#### Scenario: WIP hold GET backward compatibility
- **WHEN** `GET /api/wip/overview/hold?hold_type=quality&lotid=LOT001,LOT002` is called
- **THEN** the response SHALL return HTTP 200 unchanged from existing behavior
