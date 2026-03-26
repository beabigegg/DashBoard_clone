## ADDED Requirements

### Requirement: Portal Navigation SHALL Group Entries by Functional Drawers
The portal SHALL group navigation entries into functional drawers: reports, queries, and development tools.

#### Scenario: Drawer grouping visibility
- **WHEN** users open the portal
- **THEN** report pages and query pages SHALL appear in separate drawer groups

### Requirement: Existing Page Behavior SHALL Remain Compatible
The portal navigation refactor SHALL preserve existing target routes and lazy-load behavior for content frames.

#### Scenario: Route continuity
- **WHEN** a user selects an existing page entry from the new drawer
- **THEN** the corresponding original route SHALL be loaded without changing page business logic behavior
