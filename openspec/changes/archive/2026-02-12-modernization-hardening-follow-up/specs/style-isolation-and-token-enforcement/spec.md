## ADDED Requirements

### Requirement: Route-local token usage SHALL include fallback values outside shell scope
Route-level styles that reference shell-provided token variables SHALL define fallback values to preserve rendering correctness when rendered outside shell variable scope.

#### Scenario: Route rendered outside portal shell variable scope
- **WHEN** a route-local stylesheet references shell token variables and the page is rendered without shell-level CSS variables
- **THEN** visual-critical properties (for example header gradients) SHALL still resolve through explicit fallback token values

#### Scenario: Style governance check for unresolved shell variables
- **WHEN** style-governance validation inspects in-scope route styles
- **THEN** unresolved shell-variable references without fallback SHALL be flagged as governance failures or approved exceptions
