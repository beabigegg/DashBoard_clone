## ADDED Requirements

### Requirement: WIP Modules SHALL Reuse Shared Autocomplete and Filter Query Utilities
WIP overview and WIP detail Vite entry modules SHALL use shared frontend core utilities for autocomplete request construction and cross-filter behavior.

#### Scenario: Cross-filter autocomplete parity across WIP pages
- **WHEN** users type in workorder/lot/package/type filters on either WIP overview or WIP detail pages
- **THEN** both pages MUST generate equivalent autocomplete request parameters and return behaviorally consistent dropdown results

#### Scenario: Shared utility change propagates across both pages
- **WHEN** autocomplete mapping rules are updated in the shared core module
- **THEN** both WIP overview and WIP detail modules MUST consume the updated behavior without duplicated page-local logic edits
