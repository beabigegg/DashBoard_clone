## ADDED Requirements

### Requirement: CACHE_TTL_DATASET SHALL be configurable via environment variable
`CACHE_TTL_DATASET` SHALL be read from `os.getenv("CACHE_TTL_DATASET_SECONDS")` with a default of 7200 seconds (2 hours), replacing the current hardcoded 900-second value.

#### Scenario: Default TTL applied when env var absent
- **WHEN** `CACHE_TTL_DATASET_SECONDS` is not set in the environment
- **THEN** `CACHE_TTL_DATASET` SHALL equal 7200 seconds

#### Scenario: Custom TTL applied when env var present
- **WHEN** `CACHE_TTL_DATASET_SECONDS=1800` is set in the environment
- **THEN** `CACHE_TTL_DATASET` SHALL equal 1800 seconds

#### Scenario: TTL propagates to spool registration
- **WHEN** `store_spooled_df()` is called from `resource_dataset_cache` or `hold_dataset_cache`
- **THEN** the `ttl_seconds` argument SHALL equal the current `_CACHE_TTL` value
- **THEN** the Redis metadata key for that spool SHALL expire after `_CACHE_TTL` seconds

### Requirement: resource_dataset_cache chunk parallel degree SHALL be configurable via environment variable
`resource_dataset_cache` SHALL read parallel degree from `RESOURCE_ENGINE_PARALLEL` with a default of 1, and pass it to both base and OEE `execute_plan` calls.

#### Scenario: Default parallel=1 when env var absent
- **WHEN** `RESOURCE_ENGINE_PARALLEL` is not set
- **THEN** both base and OEE `execute_plan` calls SHALL use `parallel=1`

#### Scenario: Custom parallel applied when env var present
- **WHEN** `RESOURCE_ENGINE_PARALLEL=2` is set
- **THEN** both base and OEE `execute_plan` calls SHALL pass `parallel=2`
- **THEN** `_effective_parallelism()` inside `execute_plan` SHALL still cap at its hard ceiling

#### Scenario: Parallel value clamped to minimum 1
- **WHEN** `RESOURCE_ENGINE_PARALLEL=0` or a negative value is set
- **THEN** the resolved parallel value SHALL be `max(1, int(...))`

### Requirement: hold_dataset_cache chunk parallel degree SHALL be configurable via environment variable
`hold_dataset_cache` SHALL read parallel degree from `HOLD_ENGINE_PARALLEL` with a default of 1.

#### Scenario: Default parallel=1 when env var absent
- **WHEN** `HOLD_ENGINE_PARALLEL` is not set
- **THEN** `execute_plan` in `hold_dataset_cache` SHALL use `parallel=1`

#### Scenario: Custom parallel applied
- **WHEN** `HOLD_ENGINE_PARALLEL=2` is set
- **THEN** `execute_plan` SHALL pass `parallel=2`

### Requirement: job_query_service chunk parallel degree SHALL be configurable via environment variable
`job_query_service` SHALL read parallel degree from `JOB_ENGINE_PARALLEL` with a default of 1.

#### Scenario: Default parallel=1 when env var absent
- **WHEN** `JOB_ENGINE_PARALLEL` is not set
- **THEN** `execute_plan` in `job_query_service` SHALL use `parallel=1`

#### Scenario: Custom parallel applied
- **WHEN** `JOB_ENGINE_PARALLEL=2` is set
- **THEN** `execute_plan` SHALL pass `parallel=2`

### Requirement: production_history_service chunk parallel degree SHALL be configurable via environment variable
`production_history_service` SHALL read parallel degree from `PRODUCTION_ENGINE_PARALLEL` with a default of 1, replacing the current explicit `parallel=1` hardcode.

#### Scenario: Default parallel=1 when env var absent
- **WHEN** `PRODUCTION_ENGINE_PARALLEL` is not set
- **THEN** `execute_plan` in `production_history_service` SHALL use `parallel=1`

#### Scenario: Custom parallel applied
- **WHEN** `PRODUCTION_ENGINE_PARALLEL=2` is set
- **THEN** `execute_plan` SHALL pass `parallel=2`

### Requirement: mid_section_defect_service chunk parallel degree SHALL be configurable via environment variable
`mid_section_defect_service` SHALL read parallel degree from `MSD_ENGINE_PARALLEL` with a default of 1.

#### Scenario: Default parallel=1 when env var absent
- **WHEN** `MSD_ENGINE_PARALLEL` is not set
- **THEN** `execute_plan` in `mid_section_defect_service` SHALL use `parallel=1`

#### Scenario: Custom parallel applied
- **WHEN** `MSD_ENGINE_PARALLEL=2` is set
- **THEN** `execute_plan` SHALL pass `parallel=2`

---

## E2E Test Requirements

### Requirement: CACHE_TTL_DATASET_SECONDS env var SHALL be verified by unit test
A pytest unit test in `tests/test_resource_dataset_cache.py` (or `tests/test_batch_query_engine.py`) SHALL verify that `CACHE_TTL_DATASET` reads the env var correctly.

#### Scenario: Unit test — default TTL without env var
- **WHEN** `CACHE_TTL_DATASET_SECONDS` is not in `os.environ`
- **THEN** `constants.CACHE_TTL_DATASET` SHALL equal 7200
- **THEN** `resource_dataset_cache._CACHE_TTL` SHALL equal 7200

#### Scenario: Unit test — custom TTL via env var
- **WHEN** `monkeypatch.setenv("CACHE_TTL_DATASET_SECONDS", "1800")` is applied and the module is reloaded
- **THEN** the resolved TTL SHALL equal 1800

#### Scenario: Unit test — TTL flows into store_spooled_df call
- **WHEN** `execute_primary_query()` is called with a mocked Oracle path
- **THEN** the `ttl_seconds` argument passed to `store_spooled_df` SHALL equal `_CACHE_TTL`

### Requirement: Parallel env var per-service SHALL be verified by unit tests
A pytest unit test SHALL exist for each service confirming that the `execute_plan` `parallel` argument reflects the env var value.

#### Scenario: Unit test — resource_dataset_cache RESOURCE_ENGINE_PARALLEL
- **WHEN** `monkeypatch.setenv("RESOURCE_ENGINE_PARALLEL", "2")` is applied
- **THEN** `execute_plan` SHALL be called with `parallel=2` for both base and OEE chunks
- **THEN** a test with env var absent SHALL confirm `parallel=1` is used

#### Scenario: Unit test — hold_dataset_cache HOLD_ENGINE_PARALLEL
- **WHEN** `monkeypatch.setenv("HOLD_ENGINE_PARALLEL", "2")` is applied
- **THEN** `execute_plan` in `hold_dataset_cache` SHALL be called with `parallel=2`

#### Scenario: Unit test — job_query_service JOB_ENGINE_PARALLEL
- **WHEN** `monkeypatch.setenv("JOB_ENGINE_PARALLEL", "2")` is applied
- **THEN** `execute_plan` in `job_query_service` SHALL be called with `parallel=2`

#### Scenario: Unit test — production_history_service PRODUCTION_ENGINE_PARALLEL
- **WHEN** `monkeypatch.setenv("PRODUCTION_ENGINE_PARALLEL", "2")` is applied
- **THEN** `execute_plan` in `production_history_service` SHALL be called with `parallel=2`

#### Scenario: Unit test — mid_section_defect_service MSD_ENGINE_PARALLEL
- **WHEN** `monkeypatch.setenv("MSD_ENGINE_PARALLEL", "2")` is applied
- **THEN** `execute_plan` in `mid_section_defect_service` SHALL be called with `parallel=2`

### Requirement: resource-history POST /query e2e test SHALL verify spool reuse across warmup window
An e2e test in `tests/e2e/test_resource_history_e2e.py` SHALL verify that a second POST /query within TTL reuses the spool and does not call Oracle again.

#### Scenario: E2E — second query hits spool, no Oracle call
- **WHEN** POST /query is called once and the spool is populated
- **AND** POST /query is called again with the same parameters within TTL
- **THEN** the Oracle query function SHALL be called exactly once (not twice)
- **THEN** both responses SHALL contain the same `query_id`

#### Scenario: E2E — canonical spool path returns same query_id
- **WHEN** `try_compute_query_from_canonical_spool` returns a result
- **THEN** the response `data.query_id` SHALL equal the canonical query_id
- **THEN** no Oracle mock SHALL be called
