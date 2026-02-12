## Purpose
Define stable requirements for tailwind-design-system.
## Requirements
### Requirement: Frontend styles SHALL be governed by Tailwind design tokens
The frontend SHALL enforce a token-governed style system for in-scope routes. Shared visual semantics SHALL be expressed through token-backed Tailwind/shared layers, and ad-hoc page-local hard-coded values for shared semantics SHALL require explicit exception governance.

#### Scenario: Shared token usage across in-scope modules
- **WHEN** two in-scope modules render equivalent UI semantics (e.g., card, filter chip, primary action, status indicator)
- **THEN** they SHALL use the same token-backed style semantics
- **THEN** visual output SHALL remain consistent across those modules

#### Scenario: Token governance review
- **WHEN** an in-scope route introduces new shared UI styling
- **THEN** the styling SHALL map to shared tokens/layers or be recorded in an approved exception registry

### Requirement: Tailwind migration SHALL support coexistence with legacy CSS
Tailwind migration SHALL support controlled coexistence only as a transition state for this phase. In-scope routes SHALL move toward isolation-first style ownership and SHALL NOT introduce new page-global CSS side effects for route-local concerns.

#### Scenario: In-scope global selector control
- **WHEN** in-scope route styles are reviewed
- **THEN** new route-local styling SHALL NOT introduce page-global selectors (`:root`, `body`) for local presentation behavior

#### Scenario: Deferred route coexistence allowance
- **WHEN** deferred routes (`/tables`, `/excel-query`, `/query-tool`, `/mid-section-defect`) are evaluated during this phase
- **THEN** existing coexistence posture SHALL be allowed and handled by a follow-up modernization change

### Requirement: New shared UI components SHALL prefer Tailwind-first styling
Newly introduced shared components SHALL be implemented with Tailwind-first conventions to avoid expanding duplicated page-local CSS.

#### Scenario: Shared component adoption
- **WHEN** a new shared component is introduced in migration scope
- **THEN** its primary style contract SHALL be expressed through Tailwind utilities/components
- **THEN** page-local CSS additions SHALL be minimized and justified

