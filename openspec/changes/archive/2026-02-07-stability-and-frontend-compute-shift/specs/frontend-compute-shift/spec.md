## ADDED Requirements

### Requirement: Compute-Shifted Logic SHALL Be Exposed as Reusable Frontend Core Modules
Frontend-computed metrics and transformations MUST be implemented as reusable, testable modules instead of page-local inline logic.

#### Scenario: Multiple pages consume shared compute logic
- **WHEN** two or more pages require the same metric transformation or aggregation
- **THEN** they MUST import a shared frontend core module and produce consistent outputs

### Requirement: Frontend Compute Parity MUST Include Tolerance Contracts Per Metric
Parity verification SHALL define explicit tolerance and rounding contracts per migrated metric.

#### Scenario: Parity check for migrated metric
- **WHEN** migrated frontend computation is validated against baseline output
- **THEN** parity tests MUST evaluate the metric against its declared tolerance and fail when outside bounds

### Requirement: Compute Shift MUST Preserve Existing User-Facing Logic
Frontend compute migration MUST preserve existing filter semantics, drill-down behavior, and displayed totals.

#### Scenario: Existing dashboard interactions after compute shift
- **WHEN** users apply filters and navigate drill-down flows on migrated pages
- **THEN** interaction results MUST remain behaviorally equivalent to the pre-shift baseline
