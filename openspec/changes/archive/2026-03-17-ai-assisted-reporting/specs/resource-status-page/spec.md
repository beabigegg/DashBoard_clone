## ADDED Requirements

### Requirement: Equipment deviation detection badge
The resource-status page SHALL display a badge when equipment utilization deviations are detected by the analytics API.

#### Scenario: Badge appears when deviations exist
- **WHEN** `GET /api/analytics/equipment-deviation` returns one or more items
- **THEN** the page SHALL display a badge showing the number of equipment with deviations

#### Scenario: Badge hidden when feature flag is off
- **WHEN** the feature flag `ANALYTICS_ANOMALY_DETECTION_ENABLED` is `false`
- **THEN** the badge SHALL NOT be rendered

#### Scenario: Badge click shows deviation details
- **WHEN** the user clicks the deviation badge
- **THEN** a popover SHALL display the top-3 equipment deviations with resource name, workcenter, current OU%, baseline OU%, and deviation
