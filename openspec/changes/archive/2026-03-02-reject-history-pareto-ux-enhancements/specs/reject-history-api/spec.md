## MODIFIED Requirements

### Requirement: Reject History API SHALL provide CSV export endpoint
The API SHALL provide CSV export using the same filter and metric semantics as list/query APIs.

#### Scenario: Export payload consistency
- **WHEN** `GET /api/reject-history/export` is called with valid filters
- **THEN** CSV headers SHALL include both `REJECT_TOTAL_QTY` and `DEFECT_QTY`
- **THEN** export rows SHALL follow the same semantic definitions as summary/list endpoints

#### Scenario: Cached export supports full detail-filter parity
- **WHEN** `GET /api/reject-history/export-cached` is called with an existing `query_id`
- **THEN** the endpoint SHALL apply primary policy toggles, supplementary filters, trend-date filters, metric filter, and Pareto-selected item filters
- **THEN** returned rows SHALL match the same filtered detail dataset semantics used by `GET /api/reject-history/view`

#### Scenario: CSV encoding and escaping are stable
- **WHEN** either export endpoint returns CSV
- **THEN** response charset SHALL be `utf-8-sig`
- **THEN** values containing commas, quotes, or newlines SHALL be CSV-escaped correctly
