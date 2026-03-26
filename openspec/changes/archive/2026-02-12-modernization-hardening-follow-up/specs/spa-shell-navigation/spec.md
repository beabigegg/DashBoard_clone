## ADDED Requirements

### Requirement: Canonical redirect scope boundaries SHALL be explicit and intentional
Canonical shell direct-entry redirects SHALL apply only to governed in-scope report routes and SHALL explicitly exclude admin external targets with documented rationale.

#### Scenario: In-scope report route direct entry
- **WHEN** SPA shell mode is enabled and a user enters an in-scope report route directly
- **THEN** the system SHALL redirect to the canonical `/portal-shell/...` route while preserving query semantics

#### Scenario: Admin external target direct entry
- **WHEN** SPA shell mode is enabled and a user enters `/admin/pages` or `/admin/performance` directly
- **THEN** the system SHALL NOT apply report-route canonical redirect policy
- **THEN** the exclusion rationale SHALL be documented in code-level comments or governance docs

### Requirement: Missing-required-parameter redirects SHALL avoid avoidable multi-hop chains
Routes with server-side required query parameters SHALL minimize redirect hops under SPA shell mode.

#### Scenario: Hold detail missing reason in SPA shell mode
- **WHEN** a user opens `/hold-detail` without `reason` while SPA shell mode is enabled
- **THEN** the route SHALL resolve via a single-hop redirect to the canonical overview shell path
