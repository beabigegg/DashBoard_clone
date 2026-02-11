## Purpose
Define stable requirements for tailwind-design-system.

## Requirements

### Requirement: Frontend styles SHALL be governed by Tailwind design tokens
The frontend SHALL define a Tailwind-based design token system for color, spacing, typography, radius, and elevation to ensure consistent styling across modules.

#### Scenario: Shared token usage across modules
- **WHEN** two report modules render equivalent UI elements (e.g., card, filter chip, primary button)
- **THEN** they SHALL use the same token-backed style semantics
- **THEN** visual output SHALL remain consistent across modules

### Requirement: Tailwind migration SHALL support coexistence with legacy CSS
The migration SHALL allow Tailwind and existing page CSS to coexist during phased rollout without breaking existing pages.

#### Scenario: Legacy page remains functional during coexistence
- **WHEN** a not-yet-migrated page is rendered
- **THEN** existing CSS behavior SHALL remain intact
- **THEN** Tailwind introduction SHALL NOT cause blocking style regressions

### Requirement: New shared UI components SHALL prefer Tailwind-first styling
Newly introduced shared components SHALL be implemented with Tailwind-first conventions to avoid expanding duplicated page-local CSS.

#### Scenario: Shared component adoption
- **WHEN** a new shared component is introduced in migration scope
- **THEN** its primary style contract SHALL be expressed through Tailwind utilities/components
- **THEN** page-local CSS additions SHALL be minimized and justified
