## ADDED Requirements

### Requirement: Material Trace export SHALL stream CSV output
`POST /api/material-trace/export` SHALL stream CSV content incrementally instead of materializing full CSV bytes in memory before response.

#### Scenario: Streaming export for large result set
- **WHEN** export result contains many rows
- **THEN** response SHALL be produced via streaming generator/chunked writing
- **THEN** service SHALL not require a single in-memory CSV blob for the full dataset

#### Scenario: Streaming export preserves existing CSV contract
- **WHEN** export is streamed
- **THEN** CSV column order, BOM behavior, and filename contract SHALL remain backward-compatible

### Requirement: Material Trace query/export SHALL emit quality metadata
Material Trace query and export responses SHALL explicitly mark complete vs truncated outcomes.

#### Scenario: Forward query truncation metadata
- **WHEN** forward query exceeds configured row guard
- **THEN** query response metadata SHALL include `quality_meta.status = "truncated"`
- **THEN** metadata SHALL include truncation limit context

#### Scenario: Export truncation metadata
- **WHEN** export exceeds configured export max rows
- **THEN** export response SHALL include explicit truncation markers (response headers and metadata)
- **THEN** truncation markers SHALL be machine-readable for frontend/client handling

#### Scenario: Complete query metadata
- **WHEN** query completes without truncation
- **THEN** response SHALL include `quality_meta.status = "complete"`
