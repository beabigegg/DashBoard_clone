## ADDED Requirements

### Requirement: Oracle error coverage SHALL be split into a contract tier and a real-driver tier

The Oracle error-path test coverage SHALL comprise two explicit tiers:

1. **Contract tier (pre-merge)** — `tests/integration/test_oracle_error_codes.py`: uses `unittest.mock.patch` to inject `cx_Oracle.DatabaseError`/`oracledb.DatabaseError` instances carrying representative ORA-* code strings, verifying the error handler's *parsing and envelope mapping*. This tier runs without a real Oracle instance and completes in seconds.

2. **Real-driver tier (nightly)** — `tests/integration/test_real_oracle_fault_injection.py`: exercises the real `oracledb` driver against a real Oracle container with toxiproxy-injected network faults, verifying the *driver's real exception types, real socket reconnect, real pool accounting*. This tier runs only in nightly CI (`integration_real` marker + `oracle-fault-injection` job).

The two tiers are complementary — neither replaces the other. Contract-tier tests pin the envelope mapping logic; real-driver tests pin the runtime interaction between driver, pool, and error handler.

#### Scenario: Contract tier runs in pre-merge CI

- **WHEN** pre-merge CI executes `pytest tests/ --ignore=tests/stress`
- **THEN** `tests/integration/test_oracle_error_codes.py` SHALL run
- **THEN** `tests/integration/test_real_oracle_fault_injection.py` SHALL be collected-but-skipped (via `integration_real` marker)
- **THEN** pre-merge total runtime SHALL NOT include the real Oracle container

#### Scenario: Real-driver tier runs in nightly CI

- **WHEN** the nightly `oracle-fault-injection` job executes
- **THEN** `tests/integration/test_real_oracle_fault_injection.py` SHALL run against a real Oracle container and toxiproxy
- **THEN** the same ORA-code scenarios from the contract tier SHALL be re-verified under real driver conditions

#### Scenario: Docstring of `test_oracle_connection_leak.py` reflects actual tier

- **WHEN** a reader opens `tests/test_oracle_connection_leak.py`
- **THEN** the module docstring SHALL state that the file is a pool-bookkeeping contract tier using a mock engine
- **THEN** the docstring SHALL NOT reference a "future integration_real suite" (contract drift fixed)
- **THEN** the docstring SHALL reference `tests/integration/test_real_oracle_fault_injection.py` as the location where real Oracle connection-leak scenarios are covered

### Requirement: Real Oracle driver tests SHALL document reverse-verification

Each new test in `tests/integration/test_real_oracle_fault_injection.py` SHALL be accompanied by a documented mutation-check in the PR description: temporarily removing the corresponding error handler, pool-return logic, or `Retry-After` emission SHALL cause the specific test to FAIL. Tests that still pass after the handler is removed SHALL be rejected in review.

#### Scenario: PR description lists mutation-check outcome

- **WHEN** a PR adds or modifies tests in `test_real_oracle_fault_injection.py`
- **THEN** the description SHALL identify which line / function was temporarily removed to prove each test catches the regression
- **THEN** the reviewer SHALL verify the proof before approving

### Requirement: Real Oracle driver tests SHALL NOT supersede the mock contract tier

The existing `tests/integration/test_oracle_error_codes.py` (contract tier) SHALL remain in place and SHALL continue to run in pre-merge CI. The new real-driver tier SHALL be additive. Deleting or consolidating the contract tier into the real-driver tier is forbidden by this spec.

#### Scenario: Contract tier file remains present

- **WHEN** the repository is inspected at HEAD after this change lands
- **THEN** `tests/integration/test_oracle_error_codes.py` SHALL exist
- **THEN** its existing test functions SHALL remain callable without a real Oracle container
- **THEN** pre-merge CI SHALL continue to execute them
