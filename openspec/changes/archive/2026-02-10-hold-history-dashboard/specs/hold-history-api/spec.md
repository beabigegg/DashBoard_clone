## ADDED Requirements

### Requirement: Hold History API SHALL provide daily trend data with Redis caching
The API SHALL return daily aggregated hold/release metrics for the selected date range.

#### Scenario: Trend endpoint returns all three hold types
- **WHEN** `GET /api/hold-history/trend?start_date=2025-01-01&end_date=2025-01-31` is called
- **THEN** the response SHALL return `{ success: true, data: { days: [...] } }`
- **THEN** each day item SHALL contain `{ date, quality: { holdQty, newHoldQty, releaseQty, futureHoldQty }, non_quality: { ... }, all: { ... } }`
- **THEN** all three hold_type variants SHALL be included in a single response

#### Scenario: Trend uses shift boundary at 07:30
- **WHEN** daily aggregation is calculated
- **THEN** transactions with time >= 07:30 SHALL be attributed to the next calendar day
- **THEN** transactions with time < 07:30 SHALL be attributed to the current calendar day

#### Scenario: Trend deduplicates same-day multiple holds
- **WHEN** a lot is held multiple times on the same day
- **THEN** only one hold event SHALL be counted for that day (using ROW_NUMBER per CONTAINERID per day)

#### Scenario: Trend deduplicates future holds
- **WHEN** the same lot has multiple future holds for the same reason
- **THEN** only the first occurrence SHALL be counted (using ROW_NUMBER per CONTAINERID per HOLDREASONID)

#### Scenario: Trend hold type classification
- **WHEN** trend data is aggregated by hold type
- **THEN** quality classification SHALL use the same NON_QUALITY_HOLD_REASONS set as existing hold endpoints
- **THEN** holds with HOLDREASONNAME NOT in NON_QUALITY_HOLD_REASONS SHALL be classified as quality
- **THEN** the "all" variant SHALL include both quality and non-quality holds

#### Scenario: Trend Redis cache for recent two months
- **WHEN** the requested date range falls within the current month or previous month
- **THEN** the service SHALL check Redis for cached data at key `hold_history:daily:{YYYY-MM}`
- **THEN** if cache exists, data SHALL be returned from Redis
- **THEN** if cache is missing, data SHALL be queried from Oracle and stored in Redis with 12-hour TTL

#### Scenario: Trend direct Oracle query for older data
- **WHEN** the requested date range includes months older than the previous month
- **THEN** the service SHALL query Oracle directly without caching

#### Scenario: Trend cross-month query assembly
- **WHEN** the requested date range spans multiple months (e.g., 2025-01-15 to 2025-02-15)
- **THEN** the service SHALL fetch each month's data independently (from cache or Oracle)
- **THEN** the service SHALL trim the combined result to the exact requested date range
- **THEN** the response SHALL contain only days within start_date and end_date inclusive

#### Scenario: Trend error
- **WHEN** the database query fails
- **THEN** the response SHALL return `{ success: false, error: '查詢失敗' }` with HTTP 500

### Requirement: Hold History API SHALL provide reason Pareto data
The API SHALL return hold reason distribution for Pareto analysis.

#### Scenario: Reason Pareto endpoint
- **WHEN** `GET /api/hold-history/reason-pareto?start_date=2025-01-01&end_date=2025-01-31&hold_type=quality` is called
- **THEN** the response SHALL return `{ success: true, data: { items: [...] } }`
- **THEN** each item SHALL contain `{ reason, count, qty, pct, cumPct }`
- **THEN** items SHALL be sorted by count descending
- **THEN** pct SHALL be percentage of total hold events
- **THEN** cumPct SHALL be running cumulative percentage

#### Scenario: Reason Pareto uses shift boundary
- **WHEN** hold events are counted for Pareto
- **THEN** the 07:30 shift boundary rule SHALL be applied to HOLDTXNDATE

#### Scenario: Reason Pareto hold type filter
- **WHEN** hold_type is "quality"
- **THEN** only quality hold reasons SHALL be included
- **WHEN** hold_type is "non-quality"
- **THEN** only non-quality hold reasons SHALL be included
- **WHEN** hold_type is "all"
- **THEN** all hold reasons SHALL be included

### Requirement: Hold History API SHALL provide hold duration distribution
The API SHALL return hold duration distribution buckets.

#### Scenario: Duration endpoint
- **WHEN** `GET /api/hold-history/duration?start_date=2025-01-01&end_date=2025-01-31&hold_type=quality` is called
- **THEN** the response SHALL return `{ success: true, data: { items: [...] } }`
- **THEN** items SHALL contain 4 buckets: `{ range: "<4h", count, pct }`, `{ range: "4-24h", count, pct }`, `{ range: "1-3d", count, pct }`, `{ range: ">3d", count, pct }`

#### Scenario: Duration only includes released holds
- **WHEN** duration is calculated
- **THEN** only hold records with RELEASETXNDATE IS NOT NULL SHALL be included
- **THEN** duration SHALL be calculated as RELEASETXNDATE - HOLDTXNDATE

#### Scenario: Duration date range filter
- **WHEN** start_date and end_date are provided
- **THEN** only holds with HOLDTXNDATE within the date range (applying 07:30 shift boundary) SHALL be included

### Requirement: Hold History API SHALL provide department statistics
The API SHALL return hold/release statistics aggregated by department with optional person detail.

#### Scenario: Department endpoint
- **WHEN** `GET /api/hold-history/department?start_date=2025-01-01&end_date=2025-01-31&hold_type=quality` is called
- **THEN** the response SHALL return `{ success: true, data: { items: [...] } }`
- **THEN** each item SHALL contain `{ dept, holdCount, releaseCount, avgHoldHours, persons: [{ name, holdCount, releaseCount, avgHoldHours }] }`
- **THEN** items SHALL be sorted by holdCount descending

#### Scenario: Department with reason filter
- **WHEN** `GET /api/hold-history/department?start_date=2025-01-01&end_date=2025-01-31&hold_type=quality&reason=品質確認` is called
- **THEN** only hold records matching the specified reason SHALL be included in department and person statistics

#### Scenario: Department hold count vs release count
- **WHEN** department statistics are calculated
- **THEN** holdCount SHALL count records where HOLDEMPDEPTNAME equals the department AND HOLDTXNDATE is within the date range
- **THEN** releaseCount SHALL count records where RELEASEEMPDEPTNAME equals the department AND RELEASETXNDATE is within the date range
- **THEN** avgHoldHours SHALL be the average of (RELEASETXNDATE - HOLDTXNDATE) in hours for released holds initiated by that department

### Requirement: Hold History API SHALL provide paginated detail list
The API SHALL return a paginated list of individual hold/release records.

#### Scenario: List endpoint
- **WHEN** `GET /api/hold-history/list?start_date=2025-01-01&end_date=2025-01-31&hold_type=quality&page=1&per_page=50` is called
- **THEN** the response SHALL return `{ success: true, data: { items: [...], pagination: { page, perPage, total, totalPages } } }`
- **THEN** each item SHALL contain: lotId, workorder, workcenter, holdReason, holdDate, holdEmp, holdComment, releaseDate, releaseEmp, releaseComment, holdHours, ncr
- **THEN** items SHALL be sorted by HOLDTXNDATE descending

#### Scenario: List with reason filter
- **WHEN** `GET /api/hold-history/list?start_date=2025-01-01&end_date=2025-01-31&hold_type=quality&reason=品質確認` is called
- **THEN** only records matching the specified HOLDREASONNAME SHALL be returned

#### Scenario: List unreleased hold records
- **WHEN** a hold record has RELEASETXNDATE IS NULL
- **THEN** releaseDate SHALL be null
- **THEN** holdHours SHALL be calculated as (SYSDATE - HOLDTXNDATE) * 24

#### Scenario: List pagination bounds
- **WHEN** page is less than 1
- **THEN** page SHALL be treated as 1
- **WHEN** per_page exceeds 200
- **THEN** per_page SHALL be capped at 200

#### Scenario: List date range uses shift boundary
- **WHEN** records are filtered by date range
- **THEN** the 07:30 shift boundary rule SHALL be applied to HOLDTXNDATE

### Requirement: Hold History API SHALL use centralized SQL files
The API SHALL load SQL queries from files in the `src/mes_dashboard/sql/hold_history/` directory.

#### Scenario: SQL file organization
- **WHEN** the hold history service executes a query
- **THEN** the SQL SHALL be loaded from `sql/hold_history/<query_name>.sql`
- **THEN** the following SQL files SHALL exist: `trend.sql`, `reason_pareto.sql`, `duration.sql`, `department.sql`, `list.sql`

#### Scenario: SQL parameterization
- **WHEN** SQL queries are executed
- **THEN** all user-provided parameters (dates, hold_type, reason) SHALL be passed as bind parameters
- **THEN** no string interpolation SHALL be used for user input

### Requirement: Hold History API SHALL apply rate limiting
The API SHALL apply rate limiting to expensive endpoints.

#### Scenario: Rate limit on list endpoint
- **WHEN** the list endpoint receives excessive requests
- **THEN** rate limiting SHALL be applied using `configured_rate_limit` with a default of 90 requests per 60 seconds

#### Scenario: Rate limit on trend endpoint
- **WHEN** the trend endpoint receives excessive requests
- **THEN** rate limiting SHALL be applied using `configured_rate_limit` with a default of 60 requests per 60 seconds

### Requirement: Hold History page route SHALL serve static Vite HTML
The Flask route SHALL serve the pre-built Vite HTML file.

#### Scenario: Page route
- **WHEN** user navigates to `/hold-history`
- **THEN** Flask SHALL serve the pre-built HTML file from `static/dist/hold-history.html` via `send_from_directory`
- **THEN** the HTML SHALL NOT pass through Jinja2 template rendering

#### Scenario: Fallback HTML
- **WHEN** the pre-built HTML file does not exist
- **THEN** Flask SHALL return a minimal HTML page with the correct script tag and module import
