## ADDED Requirements

### Requirement: Yield Alert Center page SHALL abort active Job polling on unmount
When the Yield Alert Center component is destroyed (user navigates away), any active RQ Job polling controller SHALL be aborted immediately to prevent background network activity.

#### Scenario: Polling stops on navigation
- **WHEN** a user triggers a query that initiates an async RQ Job
- **AND** the user navigates away from Yield Alert Center before the job completes
- **THEN** the `_jobAbortController` SHALL be aborted in `onUnmounted`
- **THEN** no further requests SHALL be sent to the job status endpoint after component destruction
