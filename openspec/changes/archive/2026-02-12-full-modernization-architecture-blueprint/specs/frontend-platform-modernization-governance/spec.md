## ADDED Requirements

### Requirement: Frontend modernization scope SHALL be explicitly governed
The modernization program SHALL define an explicit in-scope and out-of-scope route matrix for each phase, and SHALL treat that matrix as a release-governed contract artifact.

#### Scenario: Scope matrix publication
- **WHEN** a modernization phase is created
- **THEN** the phase SHALL publish an explicit in-scope route list and out-of-scope route list
- **THEN** the matrix SHALL include `/admin/pages` and `/admin/performance` in scope for this phase
- **THEN** the matrix SHALL mark `/tables`, `/excel-query`, `/query-tool`, and `/mid-section-defect` as deferred routes for a follow-up phase

#### Scenario: Scope drift prevention
- **WHEN** implementation tasks are derived from the phase specs
- **THEN** tasks targeting routes outside the in-scope matrix SHALL be rejected for this phase

### Requirement: Modernization phases SHALL define completion and deprecation milestones
Each modernization phase SHALL define measurable completion criteria and deprecation milestones for legacy-era patterns.

#### Scenario: Phase completion criteria
- **WHEN** a phase reaches release review
- **THEN** it SHALL provide objective completion criteria for route governance, style governance, and quality gates
- **THEN** it SHALL identify any remaining deferred routes and their next-phase linkage

#### Scenario: Legacy deprecation milestones
- **WHEN** legacy fallback or legacy style exceptions remain in phase scope
- **THEN** the phase SHALL define a dated milestone or release gate to remove those exceptions
