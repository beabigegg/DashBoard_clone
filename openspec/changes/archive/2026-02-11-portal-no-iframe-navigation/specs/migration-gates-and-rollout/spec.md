## MODIFIED Requirements

### Requirement: Migration Gates SHALL Define Cutover Readiness
The system SHALL define explicit migration gates for functional parity, build integrity, drawer visibility parity, and operational health before final cutover.

#### Scenario: Gate evaluation before cutover
- **WHEN** release is prepared for final cutover
- **THEN** all required migration gates MUST pass or cutover SHALL be blocked

#### Scenario: Functional parity gate fails
- **WHEN** any critical route or core workflow parity check fails during gate execution
- **THEN** release governance MUST treat the cutover as failed and prevent promotion

### Requirement: Rollout and Rollback Procedures MUST be Actionable
The system SHALL document actionable rollout and rollback procedures for SPA-shell migration and iframe decommission.

#### Scenario: Rollback execution
- **WHEN** post-cutover validation fails critical checks
- **THEN** operators MUST be able to execute documented rollback steps to restore previous stable behavior

#### Scenario: Kill-switch rollback
- **WHEN** severe production regression is detected after cutover
- **THEN** operators MUST be able to disable the new navigation path through a documented kill-switch mechanism and recover service usability within the defined rollback target time
