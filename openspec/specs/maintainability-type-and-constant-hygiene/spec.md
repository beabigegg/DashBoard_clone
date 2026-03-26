# maintainability-type-and-constant-hygiene Specification

## Purpose
TBD - created by archiving change residual-hardening-round4. Update Purpose after archive.
## Requirements
### Requirement: Core Cache and Service Boundaries MUST Use Consistent Type Annotation Style
Core cache/service modules touched by this change SHALL use a consistent and explicit type-annotation style for public and internal helper boundaries.

#### Scenario: Reviewing updated cache/service modules
- **WHEN** maintainers inspect function signatures in affected modules
- **THEN** optional and collection types MUST follow a single consistent style and remain compatible with the project Python baseline

### Requirement: High-Frequency Magic Numbers MUST Be Replaced by Named Constants
Cache, throttling, and index-related numeric literals that control behavior MUST be extracted to named constants or env-configurable settings.

#### Scenario: Tuning cache/index behavior
- **WHEN** operators need to tune cache/index thresholds
- **THEN** they MUST find values in named constants or environment variables rather than scattered inline literals

### Requirement: Feature-flag resolution SHALL use shared helper semantics
Environment/config/default feature-flag resolution logic SHALL be implemented through shared helper utilities instead of duplicated per-module parsing.

#### Scenario: Feature-flag evaluation in app and policy modules
- **WHEN** modules resolve boolean feature flags from environment variables and Flask config
- **THEN** they SHALL use a shared helper that enforces consistent precedence and truthy/falsey parsing behavior

### Requirement: Cached policy payloads SHALL protect against shared mutable-state corruption
Policy loader functions that cache JSON payloads in-process SHALL prevent downstream callers from mutating the shared cached object reference.

#### Scenario: Cached policy payload consumed by multiple callers
- **WHEN** multiple callers read cached policy payloads during process lifetime
- **THEN** one caller's accidental mutation SHALL NOT alter another caller's observed policy state through shared reference side effects

#### Scenario: Policy cache behavior documentation
- **WHEN** maintainers inspect cached policy loader code
- **THEN** they SHALL find explicit comments describing refresh/invalidation behavior expectations

