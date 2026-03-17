## ADDED Requirements

### Requirement: Yield anomaly detection badge
The yield-alert-center page SHALL display an anomaly detection badge when statistical anomalies are detected by the analytics API.

#### Scenario: Badge appears when anomalies exist
- **WHEN** `GET /api/analytics/yield-anomalies` returns one or more items matching the current filter context
- **THEN** the page SHALL display a badge near the header showing the anomaly count

#### Scenario: Badge hidden when feature flag is off
- **WHEN** the feature flag `ANALYTICS_ANOMALY_DETECTION_ENABLED` is `false`
- **THEN** the badge SHALL NOT be rendered

#### Scenario: Badge click shows anomaly details
- **WHEN** the user clicks the anomaly badge
- **THEN** a popover SHALL display the top-3 yield anomalies with line, package, yield percentage, and Z-score
