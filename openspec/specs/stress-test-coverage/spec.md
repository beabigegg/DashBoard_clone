## Purpose

Ensure high-traffic endpoints have stress tests verifying they handle concurrent load within acceptable thresholds.

## Requirements

### Requirement: High-traffic endpoints SHALL have stress tests
Each endpoint category that serves user-facing queries SHALL have a corresponding stress test in `tests/stress/` verifying it handles concurrent load within acceptable thresholds.

#### Scenario: Endpoint category without stress test gets coverage
- **WHEN** a high-traffic endpoint category (material-trace, mid-section-defect, yield-alert, resource-history, production-history) lacks a stress test file
- **THEN** a stress test file SHALL be created using the `StressTestResult` dataclass

#### Scenario: Identified gap endpoints
- **WHEN** auditing stress test coverage for: material-trace, mid-section-defect, yield-alert, resource-history, production-history
- **THEN** each SHALL have a dedicated stress test file in `tests/stress/`

### Requirement: Stress tests SHALL use the shared StressTestResult pattern
All new stress tests SHALL use the `StressTestResult` dataclass from `tests/stress/conftest.py` and the `base_url` / `stress_config` fixtures.

#### Scenario: Stress test reports metrics
- **WHEN** a stress test completes
- **THEN** it SHALL report success_rate, avg_response_time, and requests_per_second via `StressTestResult.report()`

### Requirement: Stress tests SHALL assert minimum thresholds
Each stress test SHALL assert that the endpoint meets minimum performance thresholds under concurrent load.

#### Scenario: Success rate threshold
- **WHEN** a stress test runs with the configured number of concurrent users
- **THEN** the success rate SHALL be >= 95%

#### Scenario: Response time threshold
- **WHEN** a stress test runs with the configured number of concurrent users
- **THEN** the average response time SHALL be < 5 seconds
