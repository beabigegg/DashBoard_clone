## ADDED Requirements

### Requirement: Modernization releases SHALL pass multi-dimensional frontend quality gates
In-scope modernization releases SHALL pass functional, visual, accessibility, and performance gates before promotion.

#### Scenario: Gate bundle at release candidate
- **WHEN** a release candidate includes in-scope modernization changes
- **THEN** it SHALL execute functional behavior parity checks for affected routes
- **THEN** it SHALL execute critical-state visual regression checks for affected routes
- **THEN** it SHALL execute accessibility checks for keyboard and reduced-motion behavior
- **THEN** it SHALL execute performance budget checks for defined shell/route thresholds

### Requirement: Gate failures SHALL block release promotion
Blocking quality gates SHALL prevent release promotion for in-scope modernization changes.

#### Scenario: Blocking gate failure
- **WHEN** any mandatory modernization quality gate fails
- **THEN** release promotion SHALL be blocked until the failure is resolved or explicitly waived per governance policy

### Requirement: Deferred routes SHALL be excluded from this phase gate baseline
The route baseline for this modernization phase SHALL exclude deferred routes.

#### Scenario: Deferred route baseline exclusion
- **WHEN** gate baseline is computed for this phase
- **THEN** `/tables`, `/excel-query`, `/query-tool`, and `/mid-section-defect` SHALL be excluded from mandatory modernization gate coverage
