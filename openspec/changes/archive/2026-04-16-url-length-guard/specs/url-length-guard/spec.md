## ADDED Requirements

### Requirement: replaceRuntimeHistory SHALL guard against URL length overflow
The `replaceRuntimeHistory` function in `core/shell-navigation.js` SHALL measure the full URL before writing to `history.replaceState`. When the URL exceeds `URL_SAFE_LENGTH` (2000 characters), it SHALL store the query string in `sessionStorage` under a stable key `url-state:<pathname>` and replace the URL query with `?_s=1`.

#### Scenario: Short URL passes through unchanged
- **WHEN** `replaceRuntimeHistory('/wip-overview?status=RUN')` is called (URL < 2000 chars)
- **THEN** `history.replaceState` SHALL be called with the full URL including all query params
- **THEN** no sessionStorage entry SHALL be written

#### Scenario: Long URL spills to sessionStorage
- **WHEN** `replaceRuntimeHistory('/wip-overview?workorder=W1,W2,...,W100&lotid=L1,...,L200')` is called (URL > 2000 chars)
- **THEN** `history.replaceState` SHALL be called with `?_s=1` as the query string
- **THEN** the full original query string SHALL be stored in `sessionStorage` under key `url-state:/wip-overview`

#### Scenario: Multiple pages have independent state
- **WHEN** both `/wip-overview` and `/reject-history` have long URLs stored
- **THEN** each SHALL have its own sessionStorage entry (`url-state:/wip-overview`, `url-state:/reject-history`)
- **THEN** navigating between them SHALL NOT cause cross-contamination

### Requirement: restoreUrlState SHALL recover spilled query params on page load
A `restoreUrlState()` function SHALL be provided that checks for the `_s=1` marker in the current URL, reads the stored query string from sessionStorage, and restores it to `window.location.search` via `history.replaceState` so that downstream code (e.g., `getUrlParam`, `parseCsvParam`) reads the full parameters.

#### Scenario: Page load with _s=1 marker restores state
- **WHEN** the page loads with URL `/portal-shell/wip-overview?_s=1`
- **AND** sessionStorage contains key `url-state:/wip-overview` with value `workorder=W1,W2,...,W100&status=RUN`
- **THEN** `restoreUrlState()` SHALL call `history.replaceState` with the full query string
- **THEN** `window.location.search` SHALL contain `?workorder=W1,W2,...,W100&status=RUN`
- **THEN** the sessionStorage entry SHALL be removed after restoration

#### Scenario: Page load with _s=1 but missing sessionStorage
- **WHEN** the page loads with URL `?_s=1` but no sessionStorage entry exists (e.g., cleared or different tab)
- **THEN** `restoreUrlState()` SHALL strip the `_s=1` marker and leave the URL with no query params
- **THEN** the page SHALL load with empty/default filter state

#### Scenario: Page load without _s=1 marker
- **WHEN** the page loads with a normal URL (no `_s=1`)
- **THEN** `restoreUrlState()` SHALL be a no-op — no sessionStorage read, no URL modification

### Requirement: Cross-page navigation state SHALL transfer filters via sessionStorage
A `core/wip-navigation-state.js` module SHALL provide `storeWipNavigationState(filters, status)` and `loadWipNavigationState()` for transferring filter context between wip-overview and wip-detail without URL query params.

#### Scenario: Store navigation state before cross-page navigation
- **WHEN** `storeWipNavigationState({ workorder: ['W1','W2'], lotid: ['L1'] }, 'RUN')` is called
- **THEN** the state SHALL be stored in sessionStorage under key `wip-nav-state`
- **THEN** the stored object SHALL include a timestamp for expiry

#### Scenario: Load navigation state on destination page
- **WHEN** `loadWipNavigationState()` is called within 5 minutes of storage
- **THEN** it SHALL return the stored filters and status
- **THEN** the sessionStorage entry SHALL be consumed (removed)

#### Scenario: Expired navigation state returns null
- **WHEN** `loadWipNavigationState()` is called more than 5 minutes after storage
- **THEN** it SHALL return null
- **THEN** the page SHALL fall back to URL params or defaults

### Requirement: POST export utility SHALL download blobs without URL length risk
A `core/post-export.js` module SHALL provide a `postExport(url, body, filename)` function that sends a POST request with JSON body, receives a blob response, and triggers a browser download with the specified filename.

#### Scenario: Successful POST export
- **WHEN** `postExport('/api/reject-history/export-cached', { query_id: 'abc', packages: [...] }, 'export.csv')` is called
- **THEN** a POST request SHALL be sent with `Content-Type: application/json`
- **THEN** the response blob SHALL be downloaded as `export.csv`

#### Scenario: Export failure shows error
- **WHEN** the POST export returns a non-2xx status
- **THEN** the function SHALL throw an error with the response status
- **THEN** the calling component SHALL handle the error via its existing error banner

#### Scenario: Export 410 (dataset expired)
- **WHEN** the POST export returns HTTP 410
- **THEN** the function SHALL throw a specific error indicating dataset expiry
- **THEN** the calling component SHALL prompt the user to re-query
