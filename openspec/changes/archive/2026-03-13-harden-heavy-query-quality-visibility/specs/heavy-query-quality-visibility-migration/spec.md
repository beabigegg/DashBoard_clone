## ADDED Requirements

### Requirement: Heavy-query completeness signaling SHALL define a canonical user-facing path
The system SHALL define and enforce a canonical path for user-facing completeness signaling in heavy-query flows so that non-complete states are not hidden by route selection.

#### Scenario: Canonical path declared for MSD UI
- **WHEN** MSD page consumes staged trace aggregation for analysis rendering
- **THEN** the staged trace payload completeness fields (`quality_meta`) SHALL be treated as the canonical user-facing completeness signal
- **THEN** compatibility routes SHALL not weaken or override this completeness signal in active UI flow

### Requirement: Migration SHALL preserve completeness parity during coexistence
During migration periods where legacy and staged routes coexist, completeness semantics SHALL remain parity-safe across active and compatibility paths.

#### Scenario: Coexistence period parity gate
- **WHEN** legacy and staged paths both remain deployable for the same business flow
- **THEN** release validation SHALL include parity checks proving non-complete states remain observable in the active user path
- **THEN** migration documentation SHALL identify which route is canonical and which route is compatibility-only
