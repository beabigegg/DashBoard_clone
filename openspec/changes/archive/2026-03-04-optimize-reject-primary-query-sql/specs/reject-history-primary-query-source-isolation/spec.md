## ADDED Requirements

### Requirement: Reject-history primary query SHALL use a dedicated non-paginated SQL source
The system SHALL execute `POST /api/reject-history/query` against a dedicated primary SQL template that is isolated from the paginated list SQL contract.

#### Scenario: Direct primary path uses dedicated SQL
- **WHEN** `execute_primary_query()` runs in direct mode (no batch decomposition)
- **THEN** it SHALL compile SQL from the dedicated primary template
- **THEN** it SHALL NOT require `offset` or `limit` bind parameters for result retrieval

#### Scenario: Batch chunk path uses dedicated SQL
- **WHEN** `execute_primary_query()` runs in batch chunk mode
- **THEN** each chunk query SHALL compile SQL from the same dedicated primary template
- **THEN** chunk queries SHALL apply chunk-specific filters without relying on page-by-page replay semantics

### Requirement: Dedicated primary SQL SHALL exclude pagination-only operators
The dedicated primary SQL template SHALL avoid pagination-only constructs used by `/api/reject-history/list`.

#### Scenario: Primary SQL excludes total-count window computation
- **WHEN** the dedicated primary SQL is loaded for `/query`
- **THEN** it SHALL NOT include `COUNT(*) OVER()` as a required output field

#### Scenario: Primary SQL excludes offset-fetch pagination
- **WHEN** the dedicated primary SQL is loaded for `/query`
- **THEN** it SHALL NOT include `OFFSET ... FETCH NEXT ...` pagination clauses
