## ADDED Requirements

### Requirement: Hold outlier detection badge
The hold-overview page SHALL display a badge when hold duration outliers are detected by the analytics API.

#### Scenario: Badge appears when outliers exist
- **WHEN** `GET /api/analytics/hold-outliers` returns one or more items
- **THEN** the page SHALL display a badge showing the number of hold outliers

#### Scenario: Badge hidden when feature flag is off
- **WHEN** the feature flag `ANALYTICS_ANOMALY_DETECTION_ENABLED` is `false`
- **THEN** the badge SHALL NOT be rendered

#### Scenario: Badge click shows outlier details
- **WHEN** the user clicks the outlier badge
- **THEN** a popover SHALL display the top-3 hold outliers with lot ID, hold reason, hold hours, and the percentile threshold
