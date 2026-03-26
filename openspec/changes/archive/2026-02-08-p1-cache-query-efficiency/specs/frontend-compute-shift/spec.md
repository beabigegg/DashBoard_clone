## ADDED Requirements

### Requirement: Reusable Browser Compute Modules SHALL Power Report Derivations
Derived computations for report filters, KPI cards, chart series, and table projections SHALL be implemented through reusable frontend modules.

#### Scenario: Shared report derivation logic
- **WHEN** multiple report pages require equivalent data-shaping behavior
- **THEN** pages MUST consume shared compute modules instead of duplicating transformation logic per page

### Requirement: Browser Compute Shift SHALL Preserve Export and Field Contracts
Moving computations to frontend MUST preserve existing field naming and export column contracts.

#### Scenario: User exports report after frontend-side derivation
- **WHEN** transformed data is rendered and exported
- **THEN** exported field names and ordering MUST remain consistent with governed field contract definitions
