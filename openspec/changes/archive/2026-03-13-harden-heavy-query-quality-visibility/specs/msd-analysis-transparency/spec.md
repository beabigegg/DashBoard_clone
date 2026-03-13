## ADDED Requirements

### Requirement: MSD analysis UI SHALL surface staged completeness warnings independently of genealogy status
MSD analysis UI SHALL display a dedicated warning for non-complete staged trace results and SHALL not rely only on genealogy error status.

#### Scenario: Staged partial/truncated warning
- **WHEN** staged events aggregation contains `quality_meta.status = "partial"` or `"truncated"`
- **THEN** MSD page SHALL render a visible warning banner indicating data may be incomplete
- **THEN** the warning SHALL coexist with genealogy warning when both conditions are true

#### Scenario: Staged failed-domain warning
- **WHEN** staged events response includes failed-domain completeness metadata (`failed_domains` or equivalent failed status)
- **THEN** MSD page SHALL render diagnostics-aware warning text indicating affected scope

### Requirement: MSD compatibility route usage SHALL not hide staged completeness semantics
While compatibility endpoints remain available, active MSD UI behavior SHALL remain aligned with staged trace completeness semantics.

#### Scenario: Active UI path prioritizes staged completeness
- **WHEN** MSD UI renders summary/charts from staged events aggregation
- **THEN** completeness warning behavior SHALL be derived from staged `quality_meta`
- **THEN** absence of legacy-route warning fields SHALL NOT suppress staged non-complete warning
