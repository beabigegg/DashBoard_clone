## ADDED Requirements

### Requirement: In-scope pages SHALL enforce style isolation boundaries
In-scope modernization pages SHALL avoid page-global selectors for page-local concerns and SHALL keep style concerns scoped to route-level containers or shared design-system layers.

#### Scenario: Global selector control
- **WHEN** style governance checks analyze in-scope page styles
- **THEN** page-local style changes SHALL NOT introduce new `:root` or `body` rules for route-local presentation concerns
- **THEN** shared cross-route concerns SHALL be authored in designated shared style layers

### Requirement: In-scope shared semantics SHALL be token-first
Shared UI semantics in in-scope routes SHALL be implemented with token-backed Tailwind/shared-style primitives before page-local overrides are allowed.

#### Scenario: Token-first UI pattern adoption
- **WHEN** an in-scope route introduces or updates shared UI semantics (layout shell, card, filter, action, status)
- **THEN** the route SHALL consume token-backed shared primitives
- **THEN** page-local hard-coded visual values SHALL require explicit exception justification

### Requirement: Legacy style exceptions SHALL be tracked and sunset
Legacy CSS exceptions for in-scope routes SHALL be tracked with ownership and removal milestones.

#### Scenario: Exception registry requirement
- **WHEN** an in-scope route cannot yet remove legacy style behavior
- **THEN** the route SHALL be registered with an exception owner and planned removal milestone
- **THEN** unresolved exceptions past milestone SHALL fail modernization governance review
