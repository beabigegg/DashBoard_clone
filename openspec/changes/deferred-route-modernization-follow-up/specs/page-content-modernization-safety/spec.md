## MODIFIED Requirements

### Requirement: Deferred-route content modernization SHALL remain contract-first
Before deferred routes are cut over to modernized implementations, each route SHALL define filter/query/data-state contracts and critical interaction expectations.

#### Scenario: Deferred-route contract baseline defined
- **WHEN** `/tables`, `/excel-query`, `/query-tool`, or `/mid-section-defect` enters modernization
- **THEN** a route-level baseline SHALL capture filter input semantics, query payload shape, and critical state expectations

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

