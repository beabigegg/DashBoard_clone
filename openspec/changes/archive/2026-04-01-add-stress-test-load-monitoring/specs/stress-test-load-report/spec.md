## ADDED Requirements

### Requirement: StressTestResult SHALL support optional load summary
The `StressTestResult` dataclass SHALL accept an optional `load_summary` field of type `LoadSummary`.

#### Scenario: StressTestResult created without load summary
- **WHEN** a `StressTestResult` is created without passing `load_summary`
- **THEN** `load_summary` SHALL default to `None`
- **THEN** `report()` output SHALL be identical to the current format

#### Scenario: StressTestResult created with load summary
- **WHEN** a `StressTestResult` is created with a `LoadSummary` instance
- **THEN** `report()` SHALL append a "System Load" section after the existing metrics

### Requirement: Report SHALL include system load section when load summary is present
When `StressTestResult.load_summary` is not `None`, the `report()` method SHALL append a system load section.

#### Scenario: Report with full load metrics
- **WHEN** `report()` is called and `load_summary` has valid CPU, memory, and DB pool data
- **THEN** the report SHALL include a "System Load" section with peak CPU %, peak memory %, average CPU %, average memory %, peak DB pool %, sample count, and null sample count

#### Scenario: Report with partial load metrics
- **WHEN** `report()` is called and `load_summary` has `peak_db_pool_pct = None`
- **THEN** the DB pool line SHALL display "N/A" instead of a numeric value

### Requirement: Pytest session summary SHALL include consolidated load report
A `pytest_terminal_summary` hook in `tests/stress/conftest.py` SHALL emit a consolidated load monitoring summary at the end of the stress test session.

#### Scenario: Session with load-monitored tests
- **WHEN** the stress test session completes and at least one test recorded a `LoadSummary`
- **THEN** the terminal summary SHALL include a "Load Monitoring Summary" table with one row per test showing test name, peak CPU %, peak memory %, and peak DB pool %

#### Scenario: Session without load-monitored tests
- **WHEN** the stress test session completes and no tests recorded a `LoadSummary`
- **THEN** no additional load monitoring section SHALL appear in the terminal summary

### Requirement: run_stress_tests.py SHALL activate load collection in heavy mode
The `scripts/run_stress_tests.py` orchestrator SHALL enable load collection when running in `--heavy` mode.

#### Scenario: Heavy mode enables load collection
- **WHEN** `run_stress_tests.py` is invoked with `--heavy`
- **THEN** the environment variable `STRESS_LOAD_MONITORING=1` SHALL be set for child pytest processes

#### Scenario: Quick mode disables load collection
- **WHEN** `run_stress_tests.py` is invoked with `--quick`
- **THEN** `STRESS_LOAD_MONITORING` SHALL NOT be set (load collection disabled to minimize overhead)

#### Scenario: Explicit opt-in via flag
- **WHEN** `run_stress_tests.py` is invoked with `--load-monitor`
- **THEN** `STRESS_LOAD_MONITORING=1` SHALL be set regardless of other mode flags
