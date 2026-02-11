## MODIFIED Requirements

### Requirement: Migration Gates SHALL Define Cutover Readiness
The system SHALL define explicit migration gates for functional parity, build integrity, drawer visibility parity, route-view readiness, wrapper decommission readiness, and operational health before final cutover.

#### Scenario: Gate evaluation before cutover
- **WHEN** release is prepared for final cutover
- **THEN** all required migration gates MUST pass or cutover SHALL be blocked

#### Scenario: Functional parity gate fails
- **WHEN** any critical route or core workflow parity check fails during gate execution
- **THEN** release governance MUST treat the cutover as failed and prevent promotion

#### Scenario: Rewrite smoke checklist incomplete
- **WHEN** any page in the migration parity matrix has incomplete smoke acceptance evidence
- **THEN** final cutover SHALL be blocked

### Requirement: Rollout and Rollback Procedures MUST be Actionable
The system SHALL document actionable rollout and rollback procedures for SPA-shell migration, route-view integration, and wrapper decommission.

#### Scenario: Rollback execution
- **WHEN** post-cutover validation fails critical checks
- **THEN** operators MUST be able to execute documented rollback steps to restore previous stable behavior

#### Scenario: Kill-switch rollback
- **WHEN** severe production regression is detected after cutover
- **THEN** operators MUST be able to disable the new navigation path through a documented kill-switch mechanism and recover service usability within the defined rollback target time

#### Scenario: Partial rollback for route-view wave
- **WHEN** regressions are isolated to one or more rewritten pages
- **THEN** operators MUST be able to roll back affected pages to controlled fallback mode without breaking shell navigation for unaffected pages

## ADDED Requirements

### Requirement: Migration gates SHALL enforce shell health UX readiness
Cutover readiness SHALL include verification that shell health status is compact by default and detailed diagnostics remain available on demand.

#### Scenario: Health UX gate before release
- **WHEN** release gates are executed
- **THEN** shell header health widget MUST render summary-first behavior
- **THEN** detailed diagnostics MUST remain accessible through explicit user interaction
