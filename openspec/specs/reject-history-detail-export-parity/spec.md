# reject-history-detail-export-parity Specification

## Purpose
TBD - created by archiving change reject-history-pareto-ux-enhancements. Update Purpose after archive.
## Requirements
### Requirement: Cached reject-history export SHALL support Pareto multi-select filter parity
The cached export endpoint SHALL support Pareto multi-select context so that exported rows match the currently drilled-down detail scope.

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

