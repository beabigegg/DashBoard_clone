## ADDED Requirements

### Requirement: Page SHALL abort all pending async operations on unmount
Any page that manages long-lived async operations (RQ Job polling, fetch loops) SHALL cancel those operations when the component is unmounted, to prevent ghost network activity and stale state writes after navigation.

#### Scenario: Job polling aborted on navigation away
- **WHEN** a page has an active RQ Job polling loop
- **AND** the user navigates to a different page (component unmounts)
- **THEN** the AbortController associated with the polling SHALL be aborted
- **THEN** no further poll requests SHALL be made to the job status endpoint after unmount

#### Scenario: No ghost requests after page switch
- **WHEN** a user navigates away from a page mid-query
- **THEN** network requests initiated by that page's polling SHALL cease within one poll interval
- **THEN** reactive state (refs, reactive objects) SHALL not be updated by the aborted request

### Requirement: Query-triggering pages SHALL enforce a loading guard
Any page with a user-triggered query button SHALL prevent duplicate query submission while a query is already in flight.

#### Scenario: Rapid click protection
- **WHEN** a user clicks the query button multiple times in quick succession
- **THEN** only the first click SHALL initiate a network request
- **THEN** subsequent clicks SHALL be ignored while `loading` is true
- **THEN** the button SHALL appear disabled or non-interactive during loading

#### Scenario: Stale response discarded
- **WHEN** multiple queries are dispatched (e.g., due to filter orchestrator or watch triggers)
- **AND** an earlier query's response arrives after a newer one has started
- **THEN** the earlier response SHALL be discarded and SHALL NOT overwrite the current result
- **THEN** the page SHALL reflect only the result from the most recent query

### Requirement: Multi-composable pages SHALL clean up all composable state on unmount
Pages that compose multiple independent query composables (e.g., query-tool with multiple tabs) SHALL ensure each composable's pending request is cancelled or made stale when the page unmounts, preventing orphaned async callbacks from mutating component state.

#### Scenario: Composable cleanup on unmount
- **WHEN** a multi-tab page component is unmounted
- **THEN** all composables that expose an abort/cancel/cleanup interface SHALL have that method called
- **THEN** composables without explicit abort SHALL have their request guard ID advanced to invalidate any in-flight responses

#### Scenario: Tab switch does not corrupt sibling tab state
- **WHEN** user switches between tabs rapidly while a query is in flight on one tab
- **THEN** the response from the previously active tab's query SHALL NOT update the newly active tab's visible data
