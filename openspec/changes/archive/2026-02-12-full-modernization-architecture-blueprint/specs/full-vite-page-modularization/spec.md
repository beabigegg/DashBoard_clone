## MODIFIED Requirements

### Requirement: Major Pages SHALL be Managed by Vite Modules
The system SHALL provide Vite-managed module entries for all in-scope modernization routes under shell-first governance, including admin surfaces `/admin/pages` and `/admin/performance` as governed targets. Deferred routes (`/tables`, `/excel-query`, `/query-tool`, `/mid-section-defect`) are excluded from this phase's required module-governance completeness.

#### Scenario: In-scope module governance completeness
- **WHEN** modernization route coverage is validated for this phase
- **THEN** every in-scope route SHALL have deterministic module-governance metadata and ownership mapping

#### Scenario: Deferred route exclusion in this phase
- **WHEN** completeness validation executes for this phase
- **THEN** deferred routes SHALL be excluded from mandatory pass criteria

### Requirement: Build Pipeline SHALL Produce Backend-Served Assets
Vite build output for in-scope modernization routes MUST be emitted into backend static paths and validated at release time. Missing required in-scope assets SHALL fail release gates instead of relying on runtime fallback behavior.

#### Scenario: Build artifact readiness for in-scope routes
- **WHEN** frontend build is executed for release
- **THEN** required in-scope route artifacts SHALL be present in configured backend static dist paths
- **THEN** missing required artifacts SHALL fail readiness checks

#### Scenario: Deferred route fallback posture unchanged in this phase
- **WHEN** deferred routes are evaluated in this phase
- **THEN** existing fallback posture SHALL not block this phase's completion
