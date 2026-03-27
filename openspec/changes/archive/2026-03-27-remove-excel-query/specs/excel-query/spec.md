## REMOVED Requirements

### Requirement: Excel Query batch lookup page
The system previously provided a `/excel-query` page allowing users to perform batch queries by uploading Excel files. This feature is removed because it was only used by the previous station and is no longer needed post-launch. The feature also bypassed connection pool management via direct `get_db_connection()` calls.

**Reason**: Feature is no longer used. Removing eliminates 2 direct (non-pooled) database connections and reduces maintenance scope by ~33 files.
**Migration**: No migration needed. No active users depend on this feature.

#### Scenario: Excel Query URL returns 404
- **WHEN** a user navigates to `/excel-query`
- **THEN** the system SHALL return HTTP 404

#### Scenario: Excel Query API endpoints no longer exist
- **WHEN** a client sends a request to any `/api/excel-query/*` endpoint
- **THEN** the system SHALL return HTTP 404

#### Scenario: Portal navigation has no Excel Query entry
- **WHEN** the portal shell renders the navigation menu
- **THEN** there SHALL be no menu item or route entry for Excel Query

#### Scenario: Build output contains no Excel Query assets
- **WHEN** the frontend build (`npm run build`) completes
- **THEN** the output SHALL NOT contain `excel-query.js` or `excel-query.js.map`

#### Scenario: All existing tests pass after removal
- **WHEN** `pytest tests/ -v` is executed
- **THEN** all tests SHALL pass without excel-query-related failures

#### Scenario: No residual references in codebase
- **WHEN** a grep for `excel.query`, `excel_query`, or `excelQuery` is performed across the codebase
- **THEN** no references SHALL exist outside of git history and the openspec change directory
