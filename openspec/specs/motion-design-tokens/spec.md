## ADDED Requirements

### Requirement: Motion CSS variables defined in :root
The system SHALL define the following CSS custom properties in `:root` within `tailwind.css` `@layer base`:
- `--motion-fast: 150ms` — for checkbox, toggle micro-interactions
- `--motion-normal: 200ms` — for buttons, hover, chips
- `--motion-slow: 300ms` — for panels, overlays, sidebars
- `--motion-ease: cubic-bezier(0.4, 0, 0.2, 1)` — standard easing
- `--hover-lift: translateY(-1px)` — unified hover lift
- `--overlay-bg: rgba(255, 255, 255, 0.9)` — unified overlay background

#### Scenario: CSS variables are accessible globally
- **WHEN** any component or CSS file references `var(--motion-normal)`
- **THEN** it SHALL resolve to `200ms`

#### Scenario: Variables used in transition shorthand
- **WHEN** a component writes `transition: opacity var(--motion-normal) var(--motion-ease)`
- **THEN** the computed transition SHALL be `opacity 200ms cubic-bezier(0.4, 0, 0.2, 1)`

### Requirement: Tailwind config extends motion utilities
The system SHALL extend `tailwind.config.js` to include:
- `transitionDuration`: `fast`, `normal`, `slow` referencing the CSS variables
- `transitionTimingFunction`: `smooth` referencing `--motion-ease`

#### Scenario: Tailwind utility classes available
- **WHEN** a component uses `duration-normal` or `ease-smooth` utility classes
- **THEN** the correct CSS variable value SHALL be applied

### Requirement: No hardcoded transition times remain
After migration, no frontend CSS or Vue file SHALL contain hardcoded transition duration values (e.g., `0.12s`, `0.18s`, `0.2s`, `0.22s`, `0.3s`). All MUST reference `var(--motion-*)` tokens.

#### Scenario: Grep check passes
- **WHEN** running `grep -r "transition.*0\.\d\+s" frontend/src/ --include="*.css" | grep -v "var(--motion"`
- **THEN** zero matches SHALL be returned

### Requirement: No inconsistent hover lift values remain
After migration, all hover `transform` effects SHALL use `var(--hover-lift)`. No hardcoded `translateY(-2px)` or `translateY(-1px)` SHALL remain.

#### Scenario: Unified hover lift
- **WHEN** a user hovers over any interactive element with a lift effect
- **THEN** the element SHALL translate by exactly `var(--hover-lift)` (-1px)
