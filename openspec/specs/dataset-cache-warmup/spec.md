### Requirement: CacheUpdater SHALL pre-warm reject dataset on startup and periodically
The `CacheUpdater` SHALL invoke reject dataset loading during its periodic check cycle to ensure the dataset is always warm.

#### Scenario: Startup warmup
- **WHEN** the CacheUpdater starts its first cycle after server boot
- **THEN** it SHALL call `reject_dataset_cache.ensure_dataset_loaded()` to pre-build the reject dataset
- **THEN** if the dataset is already in Redis (from another worker), no Oracle query SHALL be executed

#### Scenario: Periodic refresh
- **WHEN** the CacheUpdater periodic cycle detects the reject dataset TTL is within 20% of expiry
- **THEN** it SHALL trigger a background refresh to prevent cold-cache gaps

#### Scenario: Warmup failure is non-fatal
- **WHEN** the reject dataset warmup fails (Oracle unreachable, timeout, etc.)
- **THEN** the CacheUpdater SHALL log a WARNING and continue its cycle
- **THEN** the failure SHALL NOT block other warmup tasks or the main CacheUpdater loop

### Requirement: CacheUpdater SHALL pre-warm yield-alert dataset
The `CacheUpdater` SHALL invoke yield-alert dataset loading during its periodic check cycle.

#### Scenario: Startup warmup
- **WHEN** the CacheUpdater starts its first cycle
- **THEN** it SHALL call `yield_alert_dataset_cache.ensure_dataset_loaded()` to pre-build the yield alert dataset

#### Scenario: Warmup failure is non-fatal
- **WHEN** the yield-alert dataset warmup fails
- **THEN** the CacheUpdater SHALL log a WARNING and continue

### Requirement: CacheUpdater SHALL pre-warm reject-history filter options
The `CacheUpdater` SHALL pre-compute reject-history filter options (the 35s cold-start endpoint).

#### Scenario: Options pre-computation
- **WHEN** the CacheUpdater warmup cycle runs
- **THEN** it SHALL call `get_filter_options()` with default parameters to populate the route-level cache

### Requirement: Dataset caches SHALL expose ensure_dataset_loaded() entry point
Each dataset cache module SHALL provide a public `ensure_dataset_loaded()` function suitable for external callers (CacheUpdater, health checks).

#### Scenario: Dataset already loaded
- **WHEN** `ensure_dataset_loaded()` is called and the dataset exists in Redis with valid TTL
- **THEN** the function SHALL return immediately without querying Oracle

#### Scenario: Dataset expired or missing
- **WHEN** `ensure_dataset_loaded()` is called and the dataset is not in Redis
- **THEN** the function SHALL execute the Oracle query and store the result in Redis

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
