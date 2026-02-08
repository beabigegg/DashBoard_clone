## ADDED Requirements

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
