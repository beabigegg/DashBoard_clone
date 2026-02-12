## ADDED Requirements

### Requirement: In-scope frontend assets SHALL be release-ready before deployment
In-scope routes SHALL rely on build/deploy readiness guarantees instead of runtime fallback behavior as the primary resilience mechanism.

#### Scenario: Build-readiness enforcement
- **WHEN** release artifacts are prepared for deployment
- **THEN** in-scope route assets SHALL be validated for presence and loadability
- **THEN** missing required in-scope assets SHALL fail the release gate

### Requirement: Runtime fallback retirement SHALL follow a governed phase policy
Runtime fallback behavior for in-scope modernization routes SHALL be retired under explicit governance milestones.

#### Scenario: Fallback retirement in phase scope
- **WHEN** a route is marked in-scope for fallback retirement
- **THEN** runtime fallback behavior for that route SHALL be removed or disabled by policy
- **THEN** reliability for that route SHALL be guaranteed by release-time readiness gates

### Requirement: Deferred routes SHALL keep existing fallback posture in this phase
Routes deferred from this modernization phase SHALL retain their existing fallback posture until handled by a follow-up change.

#### Scenario: Deferred fallback continuity
- **WHEN** `/tables`, `/excel-query`, `/query-tool`, or `/mid-section-defect` is evaluated in this phase
- **THEN** fallback retirement SHALL NOT be required for phase completion
- **THEN** fallback retirement decisions for those routes SHALL be addressed in a follow-up modernization change
