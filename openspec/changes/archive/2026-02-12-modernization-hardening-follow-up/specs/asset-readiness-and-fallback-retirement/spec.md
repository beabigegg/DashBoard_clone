## ADDED Requirements

### Requirement: Fallback-retirement failure response SHALL be consistent across route hosts
When in-scope runtime fallback retirement is enabled and route assets are unavailable, app-level and blueprint-level route handlers SHALL return a consistent retired-fallback response surface.

#### Scenario: App-level in-scope route enters retired fallback state
- **WHEN** an in-scope app-level route cannot serve required dist assets and fallback retirement is enabled
- **THEN** the route SHALL return the standardized retired-fallback response contract

#### Scenario: Blueprint-level in-scope route enters retired fallback state
- **WHEN** an in-scope blueprint-level route cannot serve required dist assets and fallback retirement is enabled
- **THEN** the route SHALL return the same standardized retired-fallback response contract used by app-level routes
