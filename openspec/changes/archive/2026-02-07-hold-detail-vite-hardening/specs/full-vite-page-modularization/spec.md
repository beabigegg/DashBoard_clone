## ADDED Requirements

### Requirement: Hold Detail Page SHALL Be Served by a Vite Module
The system SHALL provide a dedicated Vite entry bundle for the hold-detail report page.

#### Scenario: Hold-detail module asset exists
- **WHEN** `/hold-detail` is rendered and `hold-detail.js` exists in static dist
- **THEN** the page MUST load behavior from the Vite module entry

#### Scenario: Hold-detail module asset missing
- **WHEN** `/hold-detail` is rendered and the module asset is unavailable
- **THEN** the page MUST remain operational through explicit inline fallback logic
