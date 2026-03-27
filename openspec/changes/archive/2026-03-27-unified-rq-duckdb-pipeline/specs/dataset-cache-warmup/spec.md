## MODIFIED Requirements

### Requirement: Dataset warmup SHALL move from cache_updater to the spool warmup scheduler
Dataset warmups that belong to the spool pipeline SHALL be performed by the RQ-based spool warmup scheduler instead of `cache_updater`.

#### Scenario: cache_updater stops spool-pipeline dataset warmups
- **WHEN** the spool warmup scheduler is active
- **THEN** `cache_updater` SHALL NOT execute reject / yield-alert / hold dataset warmups that are now owned by the scheduler
- **THEN** `cache_updater` SHALL continue to refresh non-spool caches and reject filter options

### Requirement: Warmup coverage SHALL reflect canonical dataset readiness
Warmup coverage SHALL only expand to a report when that report has a canonical warmup identity.

#### Scenario: Immediate warmup coverage
- **WHEN** the scheduler is first enabled
- **THEN** it SHALL warm only those datasets already suitable for canonical warmup

#### Scenario: Resource-history expanded warmup coverage
- **WHEN** resource-history receives a canonical warmup key design
- **THEN** the scheduler MAY add that report in the same change

#### Scenario: Production-history remains on-demand only
- **WHEN** production-history migrates to the unified spool pipeline in this change
- **THEN** it SHALL still remain excluded from startup warmup and periodic warmup
