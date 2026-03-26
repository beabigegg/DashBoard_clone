## ADDED Requirements

### Requirement: Display-Layer Computation SHALL be Shifted to Frontend Safely
The system SHALL move eligible display-layer computations from backend to frontend while preserving existing business behavior.

#### Scenario: Equivalent metric output
- **WHEN** frontend-computed metrics are produced for a supported page
- **THEN** output values MUST match baseline backend results within defined rounding rules

### Requirement: Compute Shift MUST be Verifiable by Parity Fixtures
Each migrated computation MUST have parity fixtures comparing baseline and migrated outputs.

#### Scenario: Parity test gating
- **WHEN** a compute-shifted module is changed
- **THEN** parity checks MUST run and fail the migration gate if output differs beyond tolerance
