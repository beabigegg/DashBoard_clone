## ADDED Requirements

### Requirement: DataTable SHALL natively support fetch-triggered loading animation

#### Scenario: Fetch loading dimming via DataTable
- **WHEN** a parent component sets `DataTable`'s `:loading="true"` during a filter-triggered data fetch
- **THEN** the table body SHALL dim with `opacity: 0.4` and `pointer-events: none`
- **THEN** the transition SHALL use `var(--motion-normal)` duration
- **WHEN** loading completes and `:loading` becomes false
- **THEN** the table body SHALL animate back to `opacity: 1` with `pointer-events: auto`

#### Scenario: Content fade-in after DataTable load
- **WHEN** new data renders in DataTable after a fetch
- **THEN** the table body rows SHALL have no additional entrance animation beyond the opacity restore (to avoid jank with large datasets)
