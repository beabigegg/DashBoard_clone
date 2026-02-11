## MODIFIED Requirements

### Requirement: Frontend styles SHALL be governed by Tailwind design tokens
The frontend SHALL define a Tailwind-based design token system for color, spacing, typography, radius, and elevation to ensure consistent styling across modules. The `--portal-shell-max-width` CSS variable SHALL be set to `none` to support the fluid layout. A `--portal-sidebar-width` variable SHALL be added for sidebar width reference. The `.u-content-shell` utility class SHALL use `width: 100%` instead of `max-width` constraint.

#### Scenario: Shared token usage across modules
- **WHEN** two report modules render equivalent UI elements (e.g., card, filter chip, primary button)
- **THEN** they SHALL use the same token-backed style semantics
- **THEN** visual output SHALL remain consistent across modules

#### Scenario: Fluid layout tokens
- **WHEN** the portal shell renders
- **THEN** `--portal-shell-max-width` SHALL resolve to `none`
- **THEN** `--portal-sidebar-width` SHALL resolve to `240px`
- **THEN** `.u-content-shell` SHALL apply `width: 100%` without max-width constraint
