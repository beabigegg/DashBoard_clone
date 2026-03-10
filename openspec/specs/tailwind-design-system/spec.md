## Purpose
Define stable requirements for tailwind-design-system.
## Requirements
### Requirement: Frontend styles SHALL be governed by Tailwind design tokens
The frontend SHALL enforce `frontend/tailwind.config.js` as the single source of truth for design tokens. Shared visual semantics SHALL be expressed through token-backed Tailwind/shared layers, and token consumption in CSS SHALL use `theme()` rather than route-local token variables.

#### Scenario: Shared token usage across in-scope modules
- **WHEN** two modules render equivalent UI semantics (for example card, filter chip, primary action, status indicator)
- **THEN** they SHALL use the same token-backed semantics from `tailwind.config.js`
- **THEN** visual output SHALL remain consistent across those modules

#### Scenario: Token introduction and consumption governance
- **WHEN** a new design token is introduced
- **THEN** it SHALL be added under `theme.extend` in `frontend/tailwind.config.js`
- **THEN** CSS token consumption SHALL use `theme('...')` paths instead of introducing route-local `:root` token variables

### Requirement: Tailwind migration SHALL support coexistence with legacy CSS
Tailwind migration SHALL allow controlled legacy coexistence only as a time-bounded transition state. New or modified route styles SHALL NOT introduce additional token-like `:root` definitions or route-global selectors for local presentation behavior.

#### Scenario: In-scope global selector control
- **WHEN** route styles are reviewed during migration
- **THEN** new route-local styling SHALL NOT introduce `:root`, `body`, or `html` rules for local presentation behavior

#### Scenario: Legacy coexistence is tracked with exit criteria
- **WHEN** a route cannot complete token/theme migration in the same change
- **THEN** the route SHALL be listed in a tracked exception registry with owner and removal milestone
- **THEN** introducing new legacy patterns without an approved exception SHALL fail governance review

### Requirement: New shared UI components SHALL prefer Tailwind-first styling
Newly introduced shared components SHALL be implemented with Tailwind-first conventions to avoid expanding duplicated page-local CSS.

#### Scenario: Shared component adoption
- **WHEN** a new shared component is introduced in migration scope
- **THEN** its primary style contract SHALL be expressed through Tailwind utilities/components
- **THEN** page-local CSS additions SHALL be minimized and justified

### Requirement: Repeated shared visual semantics SHALL be abstracted into shared component classes
When equivalent visual semantics are repeated across routes, shared styling SHALL be abstracted into reusable `ui-*` component classes under `frontend/src/styles/tailwind.css` `@layer components`.

#### Scenario: Shared semantic appears repeatedly
- **WHEN** an equivalent utility/style combination appears in three or more places across route modules
- **THEN** the style SHALL be extracted as a shared `ui-*` component class
- **THEN** route modules SHALL consume the shared class instead of duplicating local declarations

