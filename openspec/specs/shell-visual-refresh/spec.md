## Purpose
Define stable requirements for portal shell visual refresh (header, sidebar, breadcrumb).

## Requirements

### Requirement: Shell header SHALL use frosted glass effect

The portal shell header SHALL enhance its visual depth with a frosted glass (glassmorphism) treatment while maintaining the brand gradient.

#### Scenario: Header backdrop blur
- **WHEN** the shell header renders
- **THEN** it SHALL apply `backdrop-filter: blur(12px)` with a semi-transparent brand gradient background (`rgba(0, 74, 118, 0.92)`)
- **THEN** it SHALL have a bottom border of `1px solid rgba(255, 255, 255, 0.1)` for subtle separation

#### Scenario: Header height adjustment
- **WHEN** the shell header renders
- **THEN** its min-height SHALL be 60px (increased from 56px)
- **THEN** `--shell-header-height` CSS variable SHALL be updated to `60px`

### Requirement: Sidebar active link SHALL display accent indicator

#### Scenario: Active link accent bar
- **WHEN** a sidebar navigation link is in active state (current route)
- **THEN** it SHALL display a left-side accent bar (3px width, `brand.500` color) via `::before` pseudo-element
- **THEN** the active link background SHALL be `surface.active` (`#e6f4fb`)

#### Scenario: Sidebar hover transition
- **WHEN** a user hovers over a sidebar navigation link
- **THEN** the background and color change SHALL transition with `var(--motion-fast)` duration

### Requirement: Sidebar drawer expand/collapse SHALL be animated

#### Scenario: Drawer content animation
- **WHEN** a sidebar drawer section expands or collapses
- **THEN** the content height change SHALL animate with `var(--motion-normal)` duration using CSS `max-height` transition

### Requirement: Breadcrumb SHALL use icon separators

#### Scenario: Chevron separator
- **WHEN** the breadcrumb displays drawer name and page title
- **THEN** the separator between segments SHALL be a Lucide `ChevronRight` icon (14px, muted color)
- **THEN** the separator SHALL replace the current `/` text separator

### Requirement: Mobile sidebar overlay SHALL use slide transition

#### Scenario: Mobile sidebar slide-in
- **WHEN** the mobile sidebar opens
- **THEN** it SHALL slide in from the left with `transform: translateX(-100%) -> translateX(0)` over `var(--motion-slow)` duration
- **THEN** the backdrop overlay SHALL fade in simultaneously with `backdrop-filter: blur(4px)`

#### Scenario: Mobile sidebar slide-out
- **WHEN** the mobile sidebar closes
- **THEN** it SHALL slide out to the left and the backdrop SHALL fade out
