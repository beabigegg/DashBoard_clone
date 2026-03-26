## ADDED Requirements

### Requirement: reject_dataset_cache batch primary execution SHALL avoid paginated replay loops
Batch chunk execution for reject-history primary query SHALL avoid page-by-page replay against paginated list SQL semantics.

#### Scenario: Chunk execution avoids offset iteration
- **WHEN** batch engine executes a reject-history chunk in `execute_primary_query()`
- **THEN** chunk execution SHALL NOT iterate through `offset` pages to assemble full chunk data
- **THEN** chunk execution SHALL retrieve chunk data via the dedicated primary SQL path

#### Scenario: Chunk bind contract excludes pagination parameters
- **WHEN** chunk query parameters are prepared for batch execution
- **THEN** `offset` and `limit` SHALL NOT be required bind variables for normal chunk retrieval

### Requirement: Partial-failure resilience SHALL remain intact after source decoupling
Decoupling from paginated list SQL SHALL NOT regress partial-failure metadata behavior.

#### Scenario: Failed chunks still produce partial-failure metadata
- **WHEN** one or more reject-history chunks fail during batch execution
- **THEN** response `meta` SHALL still report partial-failure indicators according to existing resilience contract

#### Scenario: Successful chunks still merge and continue
- **WHEN** some chunks succeed and others fail
- **THEN** the system SHALL continue to merge successful chunks and return partial results
- **THEN** progress metadata SHALL remain available for diagnostics
