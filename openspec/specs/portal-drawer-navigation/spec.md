## Purpose
Define stable requirements for portal-drawer-navigation.

## Requirements


### Requirement: Portal Navigation SHALL Group Entries by Functional Drawers
The portal SHALL group navigation entries into functional drawers as defined in the `drawers` configuration of `page_status.json`, rendered dynamically via Jinja2 loop instead of hardcoded HTML.

#### Scenario: Drawer grouping visibility
- **WHEN** users open the portal
- **THEN** the sidebar SHALL display drawers in the order defined by each drawer's `order` field
- **THEN** each drawer SHALL show only the pages assigned to it via `drawer_id`, sorted by each page's `order` field

#### Scenario: Admin-only drawer visibility
- **WHEN** a drawer has `admin_only: true` and the current user is not admin
- **THEN** the drawer and all its pages SHALL NOT be rendered in the sidebar

#### Scenario: Empty drawer visibility
- **WHEN** a drawer has no visible pages (all filtered out by `can_view_page()`)
- **THEN** the drawer group title SHALL NOT be rendered

### Requirement: Existing Page Behavior SHALL Remain Compatible
The portal navigation refactor SHALL preserve existing target routes and lazy-load behavior for content frames.

#### Scenario: Route continuity
- **WHEN** a user selects an existing page entry from a dynamically rendered drawer
- **THEN** the corresponding original route SHALL be loaded without changing page business logic behavior

#### Scenario: Iframe lazy-load continuity
- **WHEN** a sidebar item is clicked for the first time
- **THEN** the iframe SHALL lazy-load its content from the page's route, consistent with current behavior

### Requirement: First-run migration SHALL populate drawer configuration automatically
When `page_status.json` does not contain a `drawers` field, the system SHALL automatically create the default drawer structure matching the current hardcoded layout and assign existing pages to their corresponding drawers.

#### Scenario: First startup after deployment
- **WHEN** the application starts and `page_status.json` has no `drawers` field
- **THEN** the system SHALL create three default drawers (報表類, 查詢類, 開發工具)
- **THEN** the system SHALL assign each existing page to its historically correct drawer
- **THEN** the system SHALL persist the updated configuration immediately

#### Scenario: Subsequent startup
- **WHEN** the application starts and `page_status.json` already contains a `drawers` field
- **THEN** the system SHALL NOT modify the existing drawer configuration
