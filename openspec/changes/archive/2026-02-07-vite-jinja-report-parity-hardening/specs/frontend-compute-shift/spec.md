## ADDED Requirements

### Requirement: Frontend Compute Paths MUST Handle Zero and Boundary Values Correctly
Frontend-computed report metrics SHALL preserve valid zero values and boundary conditions in user-visible KPI and summary components.

#### Scenario: Zero-value KPI rendering
- **WHEN** OU% or availability metrics are computed as `0`
- **THEN** the page MUST render `0%` (or configured numeric format) instead of placeholder values

### Requirement: Hierarchical Filter Compute Logic SHALL Be Deterministic Across Levels
Frontend matrix/filter computations SHALL produce deterministic selection and filtering outcomes for group, family, and resource levels.

#### Scenario: Matrix selection at multiple hierarchy levels
- **WHEN** users toggle matrix cells across group, family, and resource rows
- **THEN** selected-state rendering and filtered equipment result sets MUST remain level-correct and reversible
