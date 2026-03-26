## Purpose
Define stable requirements for frontend-motion-system.

## Requirements

### Requirement: Navigation transitions SHALL use a maintainable baseline motion system
The frontend SHALL provide route and panel transition effects using the existing `--motion-normal` (200ms) and `--motion-fast` (150ms) CSS variables. A new `--motion-stagger` (50ms) variable SHALL be added for sequential element stagger animation (see `design-token-expansion` spec).

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

### Requirement: Motion effects SHALL preserve functional correctness
Animation implementation SHALL NOT alter data correctness, query timing semantics, or interaction outcomes.

#### Scenario: Interactive action during motion
- **WHEN** users perform filtering, refresh, or drill-down actions during transitions
- **THEN** resulting API calls and state updates SHALL remain functionally equivalent to non-animated execution
