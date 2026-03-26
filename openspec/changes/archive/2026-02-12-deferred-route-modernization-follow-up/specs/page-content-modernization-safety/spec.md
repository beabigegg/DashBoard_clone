## MODIFIED Requirements

### Requirement: Deferred-route content modernization SHALL remain contract-first
Before deferred routes are cut over to modernized implementations, each route SHALL define filter/query/data-state contracts and critical interaction expectations.

#### Scenario: Deferred-route contract baseline defined
- **WHEN** `/tables`, `/excel-query`, `/query-tool`, or `/mid-section-defect` enters modernization
- **THEN** a route-level baseline SHALL capture filter input semantics, query payload shape, and critical state expectations

### Requirement: Deferred-route implementation SHALL require pre-change confirmation
Each deferred route SHALL complete a route-scoped pre-change confirmation before implementation begins.

#### Scenario: Route enters implementation queue
- **WHEN** a deferred route is selected for modernization implementation
- **THEN** a pre-change confirmation record SHALL exist before any route code changes proceed
- **THEN** the record SHALL include current route status snapshot, baseline contract references, known-bug baseline reference, and rollback flag plan

### Requirement: Deferred-route modernization scope SHALL NOT be limited to already-released routes
Deferred modernization scope SHALL follow the deferred route matrix, even if those routes are currently marked `dev`.

#### Scenario: Route status is dev in page registry
- **WHEN** `/tables`, `/excel-query`, `/query-tool`, or `/mid-section-defect` is currently `dev`
- **THEN** the route SHALL remain eligible for modernization in this follow-up change
- **THEN** already-`released` in-scope routes outside deferred scope SHALL not be reopened by this change unless explicitly required for shared governance wiring

### Requirement: Deferred-route cutover SHALL require parity + manual acceptance
Deferred routes SHALL NOT complete cutover without parity evidence and explicit manual sign-off.

#### Scenario: Parity and sign-off before route progression
- **WHEN** a deferred route reports implementation complete
- **THEN** golden fixture parity checks and interaction parity checks SHALL pass
- **THEN** manual acceptance checklist sign-off SHALL be recorded
- **THEN** next deferred route cutover SHALL be blocked until sign-off is complete

### Requirement: Legacy bug carry-over SHALL be blocked for deferred routes
Known legacy bugs in deferred-route migrated scope SHALL be replayed during acceptance and SHALL block sign-off if reproduced.

#### Scenario: Deferred-route bug replay gate
- **WHEN** deferred-route manual acceptance executes
- **THEN** known-bug replay checks SHALL run
- **THEN** reproduced known bugs SHALL fail route sign-off and block legacy retirement
