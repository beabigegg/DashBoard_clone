## ADDED Requirements

### Requirement: Shell SHALL provide page transition on route navigation

The portal shell SHALL provide page transition effects at the native module host layer (`NativeRouteView`) using a Vue `<Transition>` wrapper around the resolved route component.

#### Scenario: Page enter transition
- **WHEN** a new route component enters the DOM
- **THEN** it SHALL animate from `opacity: 0; translateY(8px)` to `opacity: 1; translateY(0)`
- **THEN** the animation duration SHALL be `var(--motion-normal)` (200ms) with `var(--motion-ease)` easing

#### Scenario: Page leave transition
- **WHEN** the current route component leaves the DOM
- **THEN** it SHALL animate from `opacity: 1` to `opacity: 0`
- **THEN** the animation duration SHALL be `var(--motion-fast)` (150ms)

#### Scenario: Out-in transition mode
- **WHEN** transitioning between routes
- **THEN** the transition SHALL use `mode="out-in"` to prevent simultaneous rendering of old and new components

#### Scenario: Shell host RouterView remains direct render
- **WHEN** transition support is implemented
- **THEN** `portal-shell/App.vue` SHALL keep direct `<RouterView />` rendering in shell content area
- **THEN** transition wrapping SHALL be applied inside `NativeRouteView` to avoid host-level lifecycle regressions

#### Scenario: Reduced motion preference
- **WHEN** the user agent indicates `prefers-reduced-motion: reduce`
- **THEN** the page transition animations SHALL be disabled (duration: 0ms)
- **THEN** route navigation SHALL still function normally

### Requirement: Content fade-in after data load

Data-driven pages SHALL provide a subtle fade-in effect when initial data loading completes.

#### Scenario: Content appears after loading
- **WHEN** a page's initial data fetch completes and content replaces a loading state
- **THEN** the content area SHALL transition from `opacity: 0.5; translateY(4px)` to `opacity: 1; translateY(0)` over `var(--motion-normal)`

## MODIFIED Requirements

### Requirement: Navigation transitions SHALL use a maintainable baseline motion system
The frontend SHALL provide route and panel transition effects using a baseline motion mechanism suitable for long-term maintenance.

#### Scenario: Route transition feedback
- **WHEN** a user navigates between report modules
- **THEN** the shell SHALL provide consistent transition feedback via the `page-fade` CSS transition (fade-up enter, fade leave)
- **THEN** transitions SHALL NOT block route completion or data loading

### Requirement: Motion behavior SHALL support reduced-motion accessibility
The motion system SHALL respect reduced-motion user preferences.

#### Scenario: Reduced-motion preference
- **WHEN** user agent indicates reduced motion preference
- **THEN** non-essential animations SHALL be minimized or disabled (transition duration set to 0ms)
- **THEN** primary interactions SHALL remain fully usable
