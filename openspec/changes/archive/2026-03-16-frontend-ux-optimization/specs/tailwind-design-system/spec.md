## MODIFIED Requirements

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

#### Scenario: text.muted meets WCAG AA contrast
- **WHEN** `text.muted` is used on white/light backgrounds
- **THEN** the token value SHALL be `#64748b` or darker to achieve minimum 4.5:1 contrast ratio

### Requirement: Repeated shared visual semantics SHALL be abstracted into shared component classes
When equivalent visual semantics are repeated across routes, shared styling SHALL be abstracted into reusable `ui-*` component classes under `frontend/src/styles/tailwind.css` `@layer components`.

#### Scenario: Shared semantic appears repeatedly
- **WHEN** an equivalent utility/style combination appears in three or more places across route modules
- **THEN** the style SHALL be extracted as a shared `ui-*` component class
- **THEN** route modules SHALL consume the shared class instead of duplicating local declarations

#### Scenario: Global focus-visible rules in shared layer
- **WHEN** focus-visible styling is needed across all interactive elements
- **THEN** the rules SHALL be defined in `tailwind.css` `@layer components`
- **THEN** the rules SHALL use `theme()` for color values

#### Scenario: Table zebra striping in shared layer
- **WHEN** alternating row backgrounds are needed for data tables
- **THEN** the rule SHALL be defined in `tailwind.css` `@layer components` under `.ui-table-wrap`
- **THEN** the background color SHALL reference `theme('colors.surface.muted')`
