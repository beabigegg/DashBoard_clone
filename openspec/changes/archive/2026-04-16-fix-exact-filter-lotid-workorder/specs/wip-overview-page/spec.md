## MODIFIED Requirements

### Requirement: Overview page SHALL support autocomplete filtering
The page SHALL provide autocomplete-enabled filter inputs for WORKORDER, LOT ID, PACKAGE, and TYPE. Filter values selected from the dropdown list SHALL be matched against the dataset using **exact match** (case-insensitive). Fuzzy/substring search SHALL only occur at the autocomplete suggestion stage (UI layer, via `/api/wip/meta/search`); once values are applied as filters, only rows with exact field values SHALL appear in results.

#### Scenario: Autocomplete search
- **WHEN** user types 2+ characters in a filter input
- **THEN** the page SHALL call `GET /api/wip/meta/search` with debounce (300ms)
- **THEN** suggestions SHALL appear in a dropdown below the input
- **THEN** cross-filter parameters SHALL be included (other active filter values)

#### Scenario: Apply and clear filters
- **WHEN** user clicks "套用篩選" or presses Enter in a filter input
- **THEN** all three API calls (summary, matrix, hold) SHALL reload with the filter values
- **THEN** the URL SHALL be updated to reflect the applied filter values
- **WHEN** user clicks "清除篩選"
- **THEN** all filter inputs SHALL be cleared and data SHALL reload without filters
- **THEN** the URL SHALL be cleared of all filter and status parameters

#### Scenario: Active filter display
- **WHEN** filters are applied
- **THEN** active filters SHALL be displayed as removable tags (e.g., "WO: {value} ×")
- **THEN** clicking a tag's remove button SHALL clear that filter, reload data, and update the URL

#### Scenario: LOTID exact match returns only precise results
- **WHEN** user selects `LOT-123` from the LOTID filter dropdown and applies filters
- **THEN** the summary and matrix SHALL only include lots where `LOTID` exactly equals `LOT-123`
- **THEN** lots with LOTID `LOT-1234`, `XLOT-123`, or any other partial match SHALL NOT appear

#### Scenario: WORKORDER exact match returns only precise results
- **WHEN** user selects `WO001` from the WORKORDER filter dropdown and applies filters
- **THEN** results SHALL only include lots where `WORKORDER` exactly equals `WO001`
