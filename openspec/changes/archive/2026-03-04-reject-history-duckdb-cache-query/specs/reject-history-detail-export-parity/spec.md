## MODIFIED Requirements

### Requirement: Cached reject-history export SHALL support Pareto multi-select filter parity
The cached export endpoint SHALL support Pareto multi-select context so that exported rows match the currently drilled-down detail scope, and SHALL stream response output to avoid requiring full in-memory row materialization before sending data.

#### Scenario: Apply selected Pareto dimension values
- **WHEN** export request provides `pareto_dimension` and one or more `pareto_values`
- **THEN** the backend SHALL apply an OR-match filter against the mapped dimension column
- **THEN** only rows matching selected values SHALL be exported

#### Scenario: No Pareto selection keeps existing behavior
- **WHEN** `pareto_values` is absent or empty
- **THEN** export SHALL apply no extra Pareto-selected-item filter
- **THEN** existing supplementary and interactive filters SHALL still apply

#### Scenario: Invalid Pareto dimension is rejected
- **WHEN** `pareto_dimension` is not one of supported dimensions
- **THEN** API SHALL return HTTP 400 with descriptive validation error

#### Scenario: Export response is streamed
- **WHEN** cached export is requested for a large filtered dataset
- **THEN** endpoint SHALL stream CSV rows incrementally to the client
- **THEN** endpoint SHALL NOT require building a full rows list in memory before response begins

#### Scenario: Export scope matches view detail scope
- **WHEN** `view` and `export-cached` are called with the same `query_id` and filter set
- **THEN** exported rows SHALL represent the same filtered data scope as detail results
- **THEN** display-only pareto truncation rules SHALL NOT remove rows from export output
