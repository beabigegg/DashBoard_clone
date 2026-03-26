## ADDED Requirements

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
