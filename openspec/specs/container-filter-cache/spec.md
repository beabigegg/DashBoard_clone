# container-filter-cache Specification

## Purpose
TBD - created by archiving change connection-pool-filter-cache-reform. Update Purpose after archive.
## Requirements
### Requirement: Container filter cache service
The system SHALL provide a `container_filter_cache` service that caches PRODUCTLINENAME (packages) and PJ_TYPE (pj_types) values from `DWH.DW_MES_CONTAINER` using a single combined SQL query.

#### Scenario: Cache initialization at startup
- **WHEN** the application starts
- **THEN** `container_filter_cache.init()` SHALL execute a single SQL query combining `DISTINCT TRIM(PRODUCTLINENAME)` and `DISTINCT TRIM(PJ_TYPE)` from `DWH.DW_MES_CONTAINER`
- **AND** the results SHALL be stored in L1 (memory) and L2 (Redis) with a 24-hour TTL
- **AND** the query SHALL use the main pool (`read_sql_df`)

#### Scenario: Cache provides packages
- **WHEN** `get_packages()` is called
- **THEN** it SHALL return the cached list of distinct PRODUCTLINENAME values
- **AND** response time SHALL be under 10ms

#### Scenario: Cache provides pj_types
- **WHEN** `get_pj_types()` is called
- **THEN** it SHALL return the cached list of distinct PJ_TYPE values
- **AND** response time SHALL be under 10ms

#### Scenario: Cache refresh
- **WHEN** `cache_updater` triggers a 24-hour refresh cycle
- **THEN** `container_filter_cache` SHALL re-query Oracle and update both L1 and L2
- **AND** if the query fails, the previous cached values SHALL be retained (fail-open)

### Requirement: Production history uses container filter cache
`production_history_service.get_type_options()` SHALL read from `container_filter_cache.get_pj_types()` instead of executing its own Oracle query.

#### Scenario: get_type_options delegates to cache
- **WHEN** `get_type_options()` is called
- **THEN** it SHALL return values from `container_filter_cache.get_pj_types()`
- **AND** it SHALL NOT execute any SQL query

### Requirement: Reject history uses container filter cache for packages
`reject_history_service.get_filter_options()` SHALL read packages from `container_filter_cache.get_packages()`.

#### Scenario: Filter options returns cached packages
- **WHEN** `get_filter_options()` is called
- **THEN** the packages list SHALL come from `container_filter_cache.get_packages()`
- **AND** the function SHALL NOT require start_date/end_date parameters to determine package options

