## Purpose
Define stable requirements for migration-gates-and-rollout.
## Requirements
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

### Requirement: Migration Gates SHALL Include Runtime Resilience Validation
Cutover readiness gates MUST include resilience checks for pool exhaustion handling, circuit-breaker fail-fast behavior, and recovery flow.

#### Scenario: Resilience gate evaluation
- **WHEN** migration gates are executed before release
- **THEN** resilience tests MUST pass for degraded-response semantics and recovery path validation

### Requirement: Migration Gates SHALL Include Frontend Compute Parity Validation
Cutover readiness MUST include parity validation for metrics shifted from backend to frontend computation.

#### Scenario: Compute parity gate
- **WHEN** a release includes additional frontend-computed metrics
- **THEN** gate execution MUST verify parity fixtures and fail if tolerance contracts are violated

### Requirement: Rollout Procedure MUST Include Conda-Systemd-Watchdog Rehearsal
Rollout and rollback runbooks SHALL include an operational rehearsal for service start, watchdog-triggered reload, and post-restart health checks under the conda/systemd runtime contract.

#### Scenario: Pre-cutover rehearsal
- **WHEN** operators execute pre-cutover rehearsal
- **THEN** they MUST successfully complete conda-based start, worker reload, and health verification steps documented in the runbook

### Requirement: Migration Gates SHALL Enforce Architecture Documentation Consistency
Cutover governance MUST include verification that runtime architecture contracts documented for operators match implemented deployment and resilience behavior.

#### Scenario: Documentation gate before release
- **WHEN** release gates are executed for a migration or hardening change
- **THEN** project README artifacts MUST be updated to reflect current single-port runtime contract, resilience diagnostics, and frontend modularization strategy

#### Scenario: Gate fails on stale architecture contract
- **WHEN** implementation introduces resilience or module-governance changes but README architecture section remains outdated
- **THEN** release governance MUST treat the gate as failed until documentation is aligned

### Requirement: Migration gates SHALL enforce shell health UX readiness
Cutover readiness SHALL include verification that shell health status is compact by default and detailed diagnostics remain available on demand.

#### Scenario: Health UX gate before release
- **WHEN** release gates are executed
- **THEN** shell header health widget MUST render summary-first behavior
- **THEN** detailed diagnostics MUST remain accessible through explicit user interaction

