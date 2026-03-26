## ADDED Requirements

### Requirement: Hold Detail Interaction Semantics SHALL Remain Equivalent After Modularization
Migrating hold-detail to a Vite module SHALL preserve existing filter, pagination, and refresh behavior.

#### Scenario: User applies filters and paginates on hold-detail
- **WHEN** users toggle age/workcenter/package filters and navigate pages
- **THEN** returned lots, distribution highlights, and pagination state MUST remain behaviorally equivalent to baseline inline behavior
