## ADDED Requirements

### Requirement: Anomaly detection SQL runtime service
The system SHALL provide an `anomaly_detection_sql_runtime.py` service module that executes statistical anomaly detection queries on existing Parquet spool data via DuckDB in-memory SQL, following the established `reject_cache_sql_runtime.py` pattern.

#### Scenario: Service initializes with DuckDB connection
- **WHEN** the anomaly detection runtime is invoked
- **THEN** it SHALL create a DuckDB in-memory connection and register Parquet spool files from the existing Redis DataFrame cache

#### Scenario: Service is gated by feature flag
- **WHEN** the feature flag `ANALYTICS_ANOMALY_DETECTION_ENABLED` is `false`
- **THEN** all anomaly detection endpoints SHALL return `not_found_error("Feature not enabled")`

### Requirement: Yield anomaly detection via Z-score
The system SHALL detect yield anomalies by computing rolling Z-scores per line/package combination using a 7-day lookback window. An anomaly is flagged when `|z_score| > threshold` (default threshold = 2).

#### Scenario: Normal yield within threshold
- **WHEN** a line/package combination has yield percentage within 2 standard deviations of its 7-day rolling average
- **THEN** it SHALL NOT be flagged as an anomaly

#### Scenario: Yield drop exceeds threshold
- **WHEN** a line/package combination has yield percentage more than 2 standard deviations below its 7-day rolling average
- **THEN** it SHALL be flagged as an anomaly with `direction: "drop"` and the computed `z_score`

#### Scenario: Yield spike exceeds threshold
- **WHEN** a line/package combination has yield percentage more than 2 standard deviations above its 7-day rolling average
- **THEN** it SHALL be flagged as an anomaly with `direction: "spike"` and the computed `z_score`

#### Scenario: Insufficient historical data
- **WHEN** fewer than 3 data points exist in the lookback window for a line/package combination
- **THEN** the system SHALL skip Z-score computation for that combination and exclude it from results

### Requirement: Reject rate spike detection
The system SHALL detect reject rate spikes by comparing the current period's reject rate against the 7-day moving average. A spike is flagged when the percentage change exceeds a configurable threshold (default = 50%).

#### Scenario: Reject rate spike detected
- **WHEN** a workcenter group's current-day reject rate exceeds its 7-day moving average by more than 50%
- **THEN** it SHALL be flagged with `type: "reject_spike"`, the current rate, the baseline rate, and the percentage change

#### Scenario: Reject rate within normal range
- **WHEN** a workcenter group's reject rate is within 50% of its 7-day moving average
- **THEN** it SHALL NOT be flagged

### Requirement: Hold duration outlier detection
The system SHALL detect hold duration outliers using the 95th percentile of hold durations within the analysis window. Holds exceeding this threshold are flagged as outliers.

#### Scenario: Hold duration exceeds 95th percentile
- **WHEN** a hold record's duration in hours exceeds the 95th percentile of all hold durations in the analysis window
- **THEN** it SHALL be flagged with `type: "hold_outlier"`, the hold duration, and the percentile threshold

#### Scenario: Hold still active (not released)
- **WHEN** a hold has no release date
- **THEN** the system SHALL compute duration from hold date to current timestamp for comparison

### Requirement: Equipment utilization deviation detection
The system SHALL detect equipment utilization (OU%) deviations by comparing the current shift's OU% against the 30-day rolling baseline for each resource.

#### Scenario: OU% drops significantly below baseline
- **WHEN** an equipment resource's current OU% is more than 15 percentage points below its 30-day rolling average
- **THEN** it SHALL be flagged with `type: "equipment_deviation"`, the current OU%, the baseline OU%, and the deviation

### Requirement: Analytics API endpoints
The system SHALL expose anomaly detection results through RESTful API endpoints under `/api/analytics/`, using `success_response()` helpers and registered in `contract/api_inventory.md`.

#### Scenario: Yield anomalies endpoint
- **WHEN** `GET /api/analytics/yield-anomalies?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` is called
- **THEN** the system SHALL return `success_response(data)` with `data.items` containing flagged yield anomalies, each with `line`, `package`, `date`, `yield_pct`, `z_score`, `direction`

#### Scenario: Reject spikes endpoint
- **WHEN** `GET /api/analytics/reject-spikes?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` is called
- **THEN** the system SHALL return flagged reject rate spikes with `workcenter_group`, `date`, `current_rate`, `baseline_rate`, `pct_change`

#### Scenario: Hold outliers endpoint
- **WHEN** `GET /api/analytics/hold-outliers?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` is called
- **THEN** the system SHALL return flagged hold outliers with `lot_id`, `hold_reason`, `hold_hours`, `percentile_threshold`

#### Scenario: Equipment deviation endpoint
- **WHEN** `GET /api/analytics/equipment-deviation?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` is called
- **THEN** the system SHALL return flagged equipment deviations with `resource_name`, `workcenter`, `current_ou_pct`, `baseline_ou_pct`, `deviation`

#### Scenario: Rate limiting
- **WHEN** a user exceeds the configured rate limit for analytics endpoints
- **THEN** the system SHALL return a 429 response with error code `RATE_LIMIT_EXCEEDED` using the existing `configured_rate_limit()` pattern

### Requirement: Analytics route layer follows thin-route contract
The analytics API routes SHALL be defined in `src/mes_dashboard/routes/analytics_routes.py` as a Flask Blueprint. Routes SHALL only perform parameter parsing, input validation, service invocation, and response formatting — no business logic.

#### Scenario: Route delegates to service
- **WHEN** `GET /api/analytics/yield-anomalies` is called
- **THEN** `analytics_routes.py` SHALL parse query parameters (`start_date`, `end_date`, optional filters), call `anomaly_detection_sql_runtime.detect_yield_anomalies(...)`, and return the result via `success_response(data)`

#### Scenario: Route registered in API inventory
- **WHEN** the analytics routes are deployed
- **THEN** `contract/api_inventory.md` SHALL contain entries for all 4 analytics endpoints under `standard-json` classification, associated with `analytics_routes.py`

### Requirement: Anomaly detection SQL templates
The system SHALL store statistical queries as SQL template files under `src/mes_dashboard/sql/analytics/`, using `SQLLoader.load()` and `QueryBuilder` for parameterized execution.

#### Scenario: SQL templates use DuckDB window functions
- **WHEN** a yield anomaly query is executed
- **THEN** the SQL SHALL use `STDDEV_POP() OVER (PARTITION BY ... ORDER BY ... ROWS BETWEEN N PRECEDING AND 1 PRECEDING)` window functions for rolling statistics

#### Scenario: SQL templates accept filter parameters
- **WHEN** optional `workcenter_groups` or `packages` filter parameters are provided
- **THEN** the SQL SHALL apply these filters via `QueryBuilder` bind variables (not string interpolation)
