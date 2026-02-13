## ADDED Requirements

### Requirement: Reject History page SHALL be a pure Vite HTML entry
The reject-history page SHALL be built from an HTML entry and emitted as static dist assets.

#### Scenario: Vite entry registration
- **WHEN** Vite config inputs are evaluated
- **THEN** `reject-history` SHALL map to `frontend/src/reject-history/index.html`

#### Scenario: Build output artifacts
- **WHEN** `vite build` completes
- **THEN** output SHALL include `reject-history.html`, `reject-history.js`, and `reject-history.css` in `static/dist/`

### Requirement: Reject History route SHALL serve static dist HTML
The Flask route for `/reject-history` SHALL serve pre-built static HTML through `send_from_directory`.

#### Scenario: Static page serving
- **WHEN** user navigates to `/reject-history`
- **THEN** Flask SHALL serve `static/dist/reject-history.html` when the file exists
- **THEN** HTML SHALL NOT be rendered through Jinja template interpolation

#### Scenario: Dist fallback response
- **WHEN** `reject-history.html` is missing in dist
- **THEN** route SHALL return a minimal fallback HTML that still references `/static/dist/reject-history.js`

### Requirement: Reject History shell integration SHALL use native module loading
The page SHALL integrate with portal-shell native module loading policy.

#### Scenario: Native module registration
- **WHEN** shell resolves a route component for `/reject-history`
- **THEN** it SHALL dynamically import `frontend/src/reject-history/App.vue`
- **THEN** the route style bundle SHALL be loaded via registered style loaders

### Requirement: Reject History page SHALL call APIs through shared core API module
The page SHALL call backend APIs via `frontend/src/core/api.js` without legacy global dependencies.

#### Scenario: API call path
- **WHEN** reject-history page executes GET or export requests
- **THEN** requests SHALL use shared API utilities (`apiGet`/equivalent)
- **THEN** page behavior SHALL NOT depend on `window.MesApi`
