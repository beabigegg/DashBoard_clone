## MODIFIED Requirements

### Requirement: Frontend styles SHALL be governed by Tailwind design tokens

> **Note:** Token expansion requirements (shadow scale, Inter font, brand color, border radius, motion variables) are fully specified in the `design-token-expansion` delta spec. This entry tracks the capability modification for record-keeping.

The frontend SHALL enforce `frontend/tailwind.config.js` as the single source of truth for design tokens. All shared visual semantics SHALL be expressed through token-backed Tailwind utility classes or `@apply` component classes.

#### Scenario: Shared token usage across in-scope modules
- **WHEN** two modules render equivalent UI semantics (card, filter chip, primary action, status indicator)
- **THEN** they SHALL use the same token-backed semantics from `tailwind.config.js`
- **THEN** visual output SHALL remain consistent across those modules

#### Scenario: Token introduction governance
- **WHEN** a new design token is introduced
- **THEN** it SHALL be added under `theme.extend` in `frontend/tailwind.config.js`
- **THEN** CSS token consumption SHALL use `theme('...')` paths instead of introducing route-local `:root` token variables

#### Scenario: text.muted accessibility compliance
- **WHEN** `text.muted` token color is used on white/light (`surface.card`, `surface.base`) backgrounds
- **THEN** the token value SHALL be `#64748b` or darker to meet WCAG AA 4.5:1 minimum contrast ratio
