## ADDED Requirements

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
