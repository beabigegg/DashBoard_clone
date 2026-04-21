## ADDED Requirements

### Requirement: Pre-merge gate upgrade of multi-worker / Redis chaos tests SHALL be data-driven

Moving `tests/integration/test_multi_worker_concurrency.py`, `tests/integration/test_redis_chaos.py`, and `tests/integration/test_real_multi_worker.py` from the nightly-only `integration_real` tier into a required pre-merge CI check SHALL be preceded by a measurement phase that demonstrates sufficient stability. A dedicated script `scripts/measure_real_infra_stability.py` SHALL drive repeated runs of these files, aggregate results into `stability-results.jsonl`, and produce `docs/real_infra_stability_report.md` with pass rate, mean duration, p95 duration, and flakiness index per test file.

#### Scenario: Stability script produces a reproducible report

- **WHEN** `python scripts/measure_real_infra_stability.py --tests multi_worker,redis_chaos,real_multi_worker --runs 3` is executed
- **THEN** each file SHALL be run 3 times under `--run-integration-real`
- **THEN** a `stability-results.jsonl` line SHALL be appended per run with schema `{date, test, run, passed, duration, tests_run, tests_failed, retries}`
- **THEN** a summary SHALL be printed showing per-file pass rate, mean duration, p95 duration

#### Scenario: Nightly CI contributes to a rolling stability dataset

- **WHEN** the nightly schedule runs `.github/workflows/measure-stability.yml`
- **THEN** one run per file SHALL be appended to `stability-results.jsonl`
- **THEN** the file SHALL be uploaded as a CI artifact and retained for at least 30 days
- **THEN** the rolling 20-day window SHALL be observable in `docs/real_infra_stability_report.md`

### Requirement: Pre-merge gate upgrade SHALL require explicit, mathematically honest stability thresholds

The pre-merge `real-infra-smoke` job SHALL be introduced only after the stability dataset shows, over a rolling 20-day × 60-run window:
- **Pass rate = 100%** (zero failures across all 60 runs)
- **p95 wall time < 180 seconds** for each individual file

The 100% threshold is deliberate and mathematically honest: a 60-run window admits only `0/60` or `1/60` failure outcomes, giving pass rates of 100% or 98.3%. Expressing this threshold as "≥ 99%" would appear to tolerate occasional failure while in fact requiring zero — a misleading policy. To tolerate ≤ 1 failure (99.0%) the sample SHALL first be expanded to ≥ 100 runs (e.g., a 34-day × 3-file window), via a separate OpenSpec change.

Until both thresholds are met, the three files SHALL remain in the nightly-only tier and no pre-merge `real-infra-smoke` job SHALL exist.

#### Scenario: Thresholds met — gate upgrade is permitted

- **WHEN** the rolling 20-day × 60-run window contains zero failures AND each file's p95 wall time is < 180 seconds
- **THEN** a PR MAY add the `real-infra-smoke` job as a required pre-merge check
- **THEN** `docs/ci_real_infra_gate_policy.md` SHALL record the measurement window, the raw pass/fail counts, and each file's p95 at the moment of upgrade

#### Scenario: Thresholds not met — gate upgrade is blocked

- **WHEN** the rolling 20-day × 60-run window contains ≥ 1 failure OR any file's p95 wall time is ≥ 180 seconds
- **THEN** the pre-merge `real-infra-smoke` job SHALL NOT be introduced
- **THEN** each contributing flakiness root cause SHALL be tracked in `triage.md` with a follow-up `fix-<slug>` OpenSpec change

#### Scenario: Future relaxation to 99% requires expanded sample

- **WHEN** a future OpenSpec change proposes relaxing the threshold from 100% to 99.0%
- **THEN** that change SHALL first expand the rolling window to ≥ 100 runs
- **THEN** that change SHALL NOT keep the 60-run window and merely relabel the threshold as 99%
- **THEN** `docs/ci_real_infra_gate_policy.md` SHALL be updated to reflect the new window and threshold together

### Requirement: Pre-merge `real-infra-smoke` job SHALL run a bounded, dedicated subset

When the upgrade is approved, `.github/workflows/backend-tests.yml` SHALL declare a `real-infra-smoke` job that:
- Triggers on `pull_request` (required check)
- Runs only `tests/integration/test_multi_worker_concurrency.py`, `tests/integration/test_redis_chaos.py`, and `tests/integration/test_real_multi_worker.py` with `--run-integration-real`
- Has `timeout-minutes: 10`
- Is independent of (does not replace) the existing nightly `integration-real` job

#### Scenario: Pre-merge smoke executes only the three designated files

- **WHEN** a pull request triggers CI
- **THEN** `real-infra-smoke` SHALL run only the three declared files
- **THEN** it SHALL NOT run `test_real_oracle_fault_injection.py`, `test_soak_workload.py`, or other `integration_real` tests

#### Scenario: Nightly integration-real job remains unchanged

- **WHEN** the nightly schedule fires
- **THEN** the existing `nightly-integration-real` job SHALL continue to execute the full `integration_real` tier
- **THEN** the pre-merge smoke and the nightly job SHALL coexist (the nightly one is a superset)

### Requirement: Pre-merge gate SHALL be reverted automatically when post-upgrade flakiness exceeds threshold

`docs/ci_real_infra_gate_policy.md` SHALL define a revert trigger: if the `real-infra-smoke` job has a 7-day rolling flaky rate (where "flaky" = runs that went from red to green on rerun) greater than 1%, the job SHALL be reverted to nightly-only (by reverting the PR that introduced it), and each flakiness root cause SHALL spawn a follow-up `fix-<slug>` change before re-attempting the upgrade.

#### Scenario: Flaky rate exceeds threshold — job is reverted

- **WHEN** over 7 days the `real-infra-smoke` job has `flaky_count / total_runs > 0.01`
- **THEN** a revert PR SHALL be merged to remove the `real-infra-smoke` job from `backend-tests.yml`
- **THEN** the three files SHALL return to nightly-only execution
- **THEN** follow-up `fix-<slug>` OpenSpec changes SHALL be opened for each identified flakiness root cause

#### Scenario: Flaky rate within threshold — job continues

- **WHEN** over 7 days the `real-infra-smoke` job has `flaky_count / total_runs ≤ 0.01`
- **THEN** no revert SHALL be initiated
- **THEN** the job SHALL remain a required pre-merge check

### Requirement: Stability measurement artifacts SHALL be version-controlled or CI-preserved

`stability-results.jsonl` SHALL be uploaded as a CI artifact by `.github/workflows/measure-stability.yml` and retained for at least 30 days. The file SHALL NOT be committed to the repository (it is rolling data, not source). `docs/real_infra_stability_report.md` SHALL be a human-readable summary regenerated at each upgrade decision point and committed alongside the upgrade PR for reviewer audit.

#### Scenario: Stability JSONL is artifact, not source

- **WHEN** the measurement workflow runs
- **THEN** `stability-results.jsonl` SHALL be uploaded as a GitHub Actions artifact with ≥ 30-day retention
- **THEN** `stability-results.jsonl` SHALL NOT be committed to `main`

#### Scenario: Stability report is committed at upgrade decision

- **WHEN** a PR proposes upgrading the pre-merge gate
- **THEN** the PR SHALL include an updated `docs/real_infra_stability_report.md` reflecting the 20-day window used for the decision
- **THEN** the reviewer SHALL verify the report matches the CI artifact data
