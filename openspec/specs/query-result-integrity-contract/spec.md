# query-result-integrity-contract Specification

## Purpose
TBD - created by archiving change cross-tool-query-integrity-hardening. Update Purpose after archive.
## Requirements
### Requirement: High-volume query APIs SHALL emit a standardized Query Quality Meta contract
All high-volume query endpoints SHALL return a standardized `quality_meta` object describing data completeness and reliability.

#### Scenario: Complete result contract
- **WHEN** a query finishes without truncation, chunk failure, or domain failure
- **THEN** response SHALL include `quality_meta.status = "complete"`
- **THEN** response SHALL include `quality_meta.reasons = []`

#### Scenario: Partial result contract
- **WHEN** one or more chunks/domains fail but partial data is still returned
- **THEN** response SHALL include `quality_meta.status = "partial"`
- **THEN** response SHALL include machine-readable fields for impacted scope (`failed_domains` and/or `failed_ranges`)

#### Scenario: Truncated result contract
- **WHEN** a row guard or total-row guard truncates returned data
- **THEN** response SHALL include `quality_meta.status = "truncated"`
- **THEN** response SHALL include the active limit field (`max_rows` or equivalent) and observed count

### Requirement: Query Quality Meta SHALL be transport-consistent
The same completeness semantics SHALL be preserved across synchronous JSON responses, async result polling, and NDJSON streams.

#### Scenario: Sync and async parity
- **WHEN** the same query executes in sync mode and async-job mode
- **THEN** both result payloads SHALL express equivalent `quality_meta.status` and reason fields

#### Scenario: NDJSON parity
- **WHEN** async NDJSON streaming is used
- **THEN** stream output SHALL include a dedicated metadata event carrying `quality_meta`
- **THEN** `quality_meta` content SHALL match the final persisted job result

### Requirement: Non-complete results SHALL be explicitly visible to clients
Client-facing APIs and UIs SHALL not silently present partial/truncated data as complete.

#### Scenario: API response carries explicit non-complete marker
- **WHEN** `quality_meta.status` is `partial` or `truncated`
- **THEN** API response SHALL carry this marker in payload metadata (and optional response headers)

#### Scenario: UI warning for non-complete results
- **WHEN** frontend receives `quality_meta.status` other than `complete`
- **THEN** UI SHALL show a visible warning banner before charts/tables
- **THEN** warning text SHALL indicate possible data incompleteness

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

