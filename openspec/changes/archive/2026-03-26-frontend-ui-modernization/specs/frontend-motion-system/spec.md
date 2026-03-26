## MODIFIED Requirements

### Requirement: Navigation transitions SHALL use a maintainable baseline motion system

> **Note:** Page transition and route animation requirements are fully specified in the `page-transition-system` delta spec. This entry tracks the capability modification for record-keeping.

The frontend SHALL provide route and panel transition effects using the existing `--motion-normal` (200ms) and `--motion-fast` (150ms) CSS variables. A new `--motion-stagger` (50ms) variable SHALL be added for sequential element stagger animation (see `design-token-expansion` delta spec).

#### Scenario: Route transition feedback
- **WHEN** a user navigates between report modules via the portal shell
- **THEN** the shell SHALL provide consistent transition feedback via the `page-fade` CSS transition (fade-up enter at `var(--motion-normal)`, fade leave at `var(--motion-fast)`)
- **THEN** transitions SHALL NOT block route completion or data loading

### Requirement: Motion behavior SHALL support reduced-motion accessibility
The motion system SHALL respect reduced-motion user preferences.

#### Scenario: Reduced-motion preference
- **WHEN** user agent indicates `prefers-reduced-motion: reduce`
- **THEN** non-essential animations SHALL be minimized or disabled (transition duration set to 0ms)
- **THEN** primary interactions SHALL remain fully usable
