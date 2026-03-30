## Purpose

Define the aggregated anomaly summary API contract, graceful degradation behavior, feature flag gating, and the derived-result cache classification for anomaly summary and detector payloads.

## Requirements

### Requirement: Aggregated anomaly summary endpoint
The system SHALL provide `GET /api/analytics/anomaly-summary` that returns counts and severity levels for all 4 anomaly detectors in a single response. The route SHALL be defined in `analytics_routes.py` and use the `success_response()` helper.

#### Scenario: Successful summary with anomalies detected
- **WHEN** the client calls `GET /api/analytics/anomaly-summary` and the feature flag `ANALYTICS_ANOMALY_DETECTION_ENABLED` is `true`
- **THEN** the system SHALL return `success_response(data, meta=meta)` where `data` contains:
  - `total_count` (int): sum of all detector counts
  - `severity` (string): overall severity = max of individual severities
  - `breakdown` (object): keyed by `yield`, `reject`, `hold`, `equipment`, each containing `count` (int), `severity` (string), and `label` (string, 中文)

#### Scenario: No anomalies detected
- **WHEN** all 4 detectors return zero anomalies
- **THEN** `data.total_count` SHALL be `0`, `data.severity` SHALL be `"ok"`, and each breakdown entry SHALL have `count: 0` and `severity: "ok"`

#### Scenario: Severity classification per detector
- **WHEN** a detector's count is `0`
- **THEN** its severity SHALL be `"ok"`
- **WHEN** a detector's count is between `1` and `5` (inclusive)
- **THEN** its severity SHALL be `"warning"`
- **WHEN** a detector's count is greater than `5`
- **THEN** its severity SHALL be `"critical"`

### Requirement: Summary endpoint follows thin-route contract
The aggregated endpoint route SHALL only perform rate limit check, feature flag validation, and service invocation. All aggregation logic SHALL reside in `get_anomaly_summary()` within `anomaly_detection_sql_runtime.py`.

#### Scenario: Route delegates to service
- **WHEN** `GET /api/analytics/anomaly-summary` is called
- **THEN** `analytics_routes.py` SHALL apply `configured_rate_limit()`, check the feature flag, call `get_anomaly_summary()`, and return `success_response(data, meta=meta)`

### Requirement: Graceful degradation per detector
Each of the 4 internal detector calls SHALL be independently wrapped in error handling. A single detector failure SHALL NOT prevent the other detectors from reporting.

#### Scenario: One detector fails
- **WHEN** `detect_reject_spikes()` raises an exception but the other 3 succeed
- **THEN** the summary SHALL return `reject.count = 0`, `reject.severity = "ok"`, and the `meta` SHALL include a `degraded` array listing `"reject"` as the failed detector

#### Scenario: All detectors fail
- **WHEN** all 4 detector calls fail
- **THEN** the summary SHALL return `total_count = 0`, `severity = "ok"`, and `meta.degraded` SHALL list all 4 detector names

### Requirement: Feature flag gating
The summary endpoint SHALL be gated by the same `ANALYTICS_ANOMALY_DETECTION_ENABLED` feature flag as the individual detector endpoints.

#### Scenario: Feature flag disabled
- **WHEN** `ANALYTICS_ANOMALY_DETECTION_ENABLED` is `false`
- **THEN** the endpoint SHALL return `not_found_error("功能未啟用")`

### Requirement: Rate limiting
The summary endpoint SHALL use the same rate limit bucket as the existing analytics endpoints.

#### Scenario: Rate limit exceeded
- **WHEN** a user exceeds the configured rate limit
- **THEN** the system SHALL return a 429 response with error code `RATE_LIMIT_EXCEEDED`

### Requirement: API inventory registration
The new endpoint SHALL be registered in `contract/api_inventory.md`.

#### Scenario: Inventory updated
- **WHEN** this change is deployed
- **THEN** `contract/api_inventory.md` SHALL include `GET /api/analytics/anomaly-summary` in the `analytics_routes.py` row under `standard-json` classification

### Requirement: Anomaly computation SHALL consume canonical source dataset identities
The anomaly layer SHALL compute derived results from canonical source dataset identities and SHALL not act as the owner of source dataset warmup for user-facing heavy-query domains.

#### Scenario: Source dataset already available
- **WHEN** anomaly computation begins and the required canonical source datasets already exist
- **THEN** the anomaly layer SHALL consume those canonical source dataset identities to compute derived results

#### Scenario: Source dataset unavailable
- **WHEN** anomaly computation cannot resolve a required canonical source dataset
- **THEN** the anomaly layer SHALL report the source dataset as unavailable or degraded
- **THEN** the anomaly layer SHALL not become the implicit steady-state warmup mechanism for that source dataset

### Requirement: Anomaly summary and detail payloads SHALL be treated as derived-result cache
Anomaly summary and detector detail payloads SHALL be stored as compact derived results rather than as source dataset substitutes.

#### Scenario: Derived result publication
- **WHEN** anomaly computation completes
- **THEN** Redis MAY store summary and detector detail payloads for replay
- **THEN** those payloads SHALL remain materially smaller than the underlying source datasets
- **THEN** clients SHALL not treat anomaly payloads as a replacement for the source heavy-query datasets
