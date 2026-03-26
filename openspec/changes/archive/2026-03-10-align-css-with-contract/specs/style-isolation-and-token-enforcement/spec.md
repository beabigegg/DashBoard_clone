## ADDED Requirements

### Requirement: Route templates SHALL avoid static inline style attributes
Vue route templates SHALL NOT use static `style="..."` for presentational styling. Dynamic computed styling MAY use `:style` when class-based expression is not sufficient.

#### Scenario: Static inline style is introduced in route template
- **WHEN** a governance check scans `.vue` templates under `frontend/src`
- **THEN** any static `style="..."` usage SHALL fail the check
- **THEN** `:style` bindings for runtime-calculated values SHALL remain allowed

## MODIFIED Requirements

### Requirement: In-scope pages SHALL enforce style isolation boundaries
All shell-governed routes and their route-local stylesheets SHALL enforce style isolation boundaries and SHALL avoid page-global selectors for route-local concerns. Shared cross-route concerns SHALL be authored only in designated shared style layers.

#### Scenario: Global selector control
- **WHEN** style governance checks analyze route-local styles under `frontend/src/**/(style|styles).css`
- **THEN** route-local styles SHALL NOT define `:root`, `body`, `html`, or universal reset selectors for local presentation concerns
- **THEN** global reset/base rules SHALL be authored only in `frontend/src/styles/tailwind.css` `@layer base`

#### Scenario: Theme root enforcement for route-local rules
- **WHEN** a route stylesheet defines selectors for route presentation
- **THEN** those selectors SHALL be scoped under a route theme root class (for example `.theme-resource`, `.theme-wip`, or route-equivalent naming)
- **THEN** unscoped top-level selectors that can leak across routes SHALL fail governance review unless explicitly approved as shared-layer semantics

#### Scenario: Shell multi-route load does not cause style leakage
- **WHEN** users navigate across multiple shell routes that keep previously loaded CSS in memory
- **THEN** route-local class rules SHALL remain bounded to their route theme root scope
- **THEN** shared class names SHALL NOT alter visual output outside their owning theme scope

### Requirement: Route-local token usage SHALL include fallback values outside shell scope
Route-level styles that reference shell-provided token variables SHALL include fallback behavior for standalone rendering or use direct `theme()` token resolution such that rendering remains correct outside shell variable scope.

#### Scenario: Route rendered outside portal shell variable scope
- **WHEN** a route is rendered without shell-level CSS variables
- **THEN** visual-critical styles SHALL still resolve using explicit fallback values or `theme()` token output

#### Scenario: Style governance check for unresolved shell variables
- **WHEN** style-governance validation inspects route styles
- **THEN** unresolved shell-variable references without fallback SHALL be flagged as governance failures or documented temporary exceptions
