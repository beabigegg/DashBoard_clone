## ADDED Requirements

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
