## ADDED Requirements

### Requirement: Completeness metadata SHALL be route-mode consistent for equivalent detail queries
Equivalent detail queries executed through different route modes SHALL preserve the same completeness semantics.

#### Scenario: Single and batch mode parity
- **WHEN** the same EventFetcher-backed query is executed as single-item mode and as batch mode with one item
- **THEN** both responses SHALL expose equivalent `quality_meta.status` and diagnostics fields
- **THEN** the active client SHALL not lose incompleteness visibility because of mode selection

### Requirement: Completeness metadata SHALL survive fallback and replay paths
Fallback execution paths and cached replay paths SHALL preserve non-complete metadata visibility.

#### Scenario: Cache replay parity
- **WHEN** a response with non-complete `quality_meta` is stored and later served from cache
- **THEN** replayed payload SHALL preserve non-complete completeness semantics

#### Scenario: Runtime fallback parity
- **WHEN** a view/runtime fallback path is used instead of the preferred runtime path
- **THEN** returned payload SHALL not silently upgrade non-complete state to `complete`
