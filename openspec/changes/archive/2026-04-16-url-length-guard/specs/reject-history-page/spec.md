## MODIFIED Requirements

### Requirement: Reject History page SHALL support CSV export from current filter context
The page SHALL allow users to export records using the exact active filters. The export request SHALL use POST with JSON body instead of GET with query string to avoid URL length limits.

#### Scenario: Export with all active filters
- **WHEN** user clicks "匯出 CSV"
- **THEN** export request SHALL be sent as POST to `/api/reject-history/export-cached` with JSON body containing query_id, supplementary filters, trend-date filters, metric filters, and Pareto selections
- **THEN** downloaded file SHALL contain exactly the same rows currently represented by the detail list filter context

#### Scenario: Export remains UTF-8 Excel compatible
- **WHEN** CSV export is downloaded
- **THEN** the file SHALL be encoded in UTF-8 with BOM
- **THEN** Chinese headers and values SHALL render correctly in common spreadsheet tools

#### Scenario: Export with large filter set does not trigger 400 error
- **WHEN** user clicks export with 50+ packages, 30+ workcenter groups, and 20+ reasons selected
- **THEN** the POST body SHALL carry all filter values without URL length concern
- **THEN** no `400 Bad Request` error SHALL occur
