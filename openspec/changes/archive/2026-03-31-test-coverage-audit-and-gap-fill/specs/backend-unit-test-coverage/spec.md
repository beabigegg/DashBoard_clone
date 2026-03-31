## ADDED Requirements

### Requirement: Every backend service SHALL have a dedicated unit test file
Each Python service module under `src/mes_dashboard/services/` SHALL have a corresponding `tests/test_<module>.py` file that tests its public API in isolation (with external dependencies mocked).

#### Scenario: Service with no existing test file gets a new test
- **WHEN** a service file exists at `services/<name>.py` with no corresponding `tests/test_<name>.py`
- **THEN** a new test file SHALL be created covering at least the primary public functions of that service

#### Scenario: Identified gap services
- **WHEN** auditing the following services: `sql_fragments.py`, `user_usage_kpi_service.py`, `anomaly_detection_sql_runtime.py`, `material_trace_duckdb_runtime.py`, `yield_alert_sql_runtime.py`, `reject_cache_sql_runtime.py`, `resource_history_sql_runtime.py`, `hold_history_sql_runtime.py`, `production_history_sql_runtime.py`, `ai_business_context.py`, `navigation_contract.py`, `yield_alert_contracts.py`, `dashboard_service.py`
- **THEN** each SHALL have a dedicated test file with at least one test per public function

### Requirement: Unit tests SHALL use the Flask test client fixture
All new backend unit tests SHALL use the `app` and `client` fixtures from `tests/conftest.py` for any tests requiring Flask application context.

#### Scenario: Test requires app context
- **WHEN** a service function accesses Flask globals (config, g, current_app)
- **THEN** the test SHALL use the `app` fixture to provide application context

### Requirement: Unit tests SHALL mock external dependencies
Unit tests SHALL mock Oracle DB connections, Redis clients, and external HTTP calls so they run without infrastructure.

#### Scenario: Service calls Oracle DB
- **WHEN** a service function executes SQL against Oracle
- **THEN** the test SHALL mock the database connection and provide fixture data

#### Scenario: Service calls Redis
- **WHEN** a service function reads/writes Redis cache
- **THEN** the test SHALL mock the Redis client or use `REDIS_ENABLED=false` environment variable
