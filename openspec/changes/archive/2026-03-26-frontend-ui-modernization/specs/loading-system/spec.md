## ADDED Requirements

### Requirement: DataTable SHALL use LoadingOverlay pattern internally

#### Scenario: Table loading state
- **WHEN** `DataTable` has `:loading="true"`
- **THEN** it SHALL apply the `.ui-table-wrap.is-loading` pattern: `opacity: 0.4`, `pointer-events: none`, `transition: opacity var(--motion-normal) var(--motion-ease)`
- **THEN** it SHALL NOT render a separate `LoadingOverlay` component to avoid double-overlay
