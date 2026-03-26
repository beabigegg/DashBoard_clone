## ADDED Requirements

### Requirement: MultiSelect loading animation SHALL align with shared motion baseline
The MultiSelect loading indicator SHALL align with shared loading motion tokens and SHALL avoid page-specific animation definitions.

#### Scenario: MultiSelect trigger loading animation
- **WHEN** `MultiSelect` has `loading=true`
- **THEN** the trigger spinner SHALL use the shared motion baseline for loading animation
- **THEN** animation behavior SHALL remain consistent with reduced-motion requirements

### Requirement: MultiSelect loading UI SHALL remain component-scoped
The MultiSelect loading state UI SHALL remain implemented within the shared component and SHALL NOT require feature pages to define local loading-spinner styles.

#### Scenario: Feature page uses MultiSelect loading
- **WHEN** a feature page passes `:loading` to `MultiSelect`
- **THEN** loading indicator rendering and animation SHALL be provided by the shared component
- **THEN** feature CSS SHALL not need to add page-specific spinner classes for MultiSelect loading
