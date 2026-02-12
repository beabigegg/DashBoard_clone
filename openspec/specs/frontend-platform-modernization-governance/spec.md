# frontend-platform-modernization-governance Specification

## Purpose
TBD - created by archiving change full-modernization-architecture-blueprint. Update Purpose after archive.
## Requirements
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

### Requirement: Operator-facing environment defaults SHALL be onboarding-safe
`.env.example` SHALL prioritize local onboarding safety while clearly documenting production hardening recommendations for modernization controls.

#### Scenario: Local bootstrap from `.env.example`
- **WHEN** a developer initializes `.env` from `.env.example` in a local non-production environment
- **THEN** startup-critical modernization flags SHALL default to onboarding-safe values that do not fail boot solely because dist readiness gates are strict by default

#### Scenario: Production recommendation visibility
- **WHEN** operators review `.env.example` for deployment configuration
- **THEN** production-recommended values for shell-first and modernization-hardening flags SHALL be explicitly documented in adjacent comments

### Requirement: Policy cache refresh model SHALL be explicit in governance docs
Governance-owned policy artifacts that are loaded with in-process caching SHALL document runtime refresh behavior and operator expectations.

#### Scenario: Cached policy artifact behavior documentation
- **WHEN** maintainers read modernization governance artifacts
- **THEN** they SHALL find explicit guidance on whether policy JSON updates require process restart, cache clear, or automatic reload

