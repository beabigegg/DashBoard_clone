## MODIFIED Requirements

### Requirement: CSV export SHALL include OEE% column
The CSV export SHALL include OEE-related fields alongside existing columns. The export request SHALL use POST with JSON body instead of GET with query string to avoid URL length limits.

#### Scenario: Export with OEE data
- **WHEN** user exports resource history data to CSV
- **THEN** the CSV SHALL include columns: `OEE%`, `Yield%`, `TRACKOUT_QTY`, `NG_QTY`
- **THEN** OEE% SHALL appear between OU% and AVAIL%, followed by Yield%, TRACKOUT_QTY, NG_QTY after AVAIL%

#### Scenario: Export uses POST to avoid URL length limits
- **WHEN** user clicks export with many workcenter_groups, families, and resource_ids selected
- **THEN** the export request SHALL be sent as POST to `/api/resource/history/export` with JSON body
- **THEN** no `400 Bad Request` error SHALL occur regardless of filter set size

#### Scenario: Export download triggers file save
- **WHEN** POST export returns successfully
- **THEN** the response blob SHALL be downloaded with filename `resource_history_{start}_{end}.csv`
