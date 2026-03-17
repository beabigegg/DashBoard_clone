## ADDED Requirements

### Requirement: Reject spike detection badge
The reject-history page SHALL display a warning badge when reject rate spikes are detected by the analytics API.

#### Scenario: Badge appears when spikes exist
- **WHEN** `GET /api/analytics/reject-spikes` returns one or more items for the current date range
- **THEN** the page SHALL display a warning badge showing the number of workcenter groups with spikes

#### Scenario: Badge hidden when feature flag is off
- **WHEN** the feature flag `ANALYTICS_ANOMALY_DETECTION_ENABLED` is `false`
- **THEN** the badge SHALL NOT be rendered

#### Scenario: Badge click shows spike details
- **WHEN** the user clicks the spike badge
- **THEN** a popover SHALL display the top-3 reject spikes with workcenter group, current rate, baseline rate, and percentage change
