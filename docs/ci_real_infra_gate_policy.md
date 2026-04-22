# CI Real-Infra Gate Policy

> **Status**: Stage 4a shipped on 2026-04-23 (informational, non-required).
> Stage 4b (required-check promotion) is blocked on the stability window
> defined below.  This document is the **single source of truth** for the
> gate-upgrade decision.
>
> **Related spec**: `openspec/changes/harden-real-infra-test-coverage/specs/multi-worker-concurrency-test-coverage/spec.md`
> (delta spec; will be archived into main spec after Phase 4b promotion)

## 1. Purpose

The `real-infra-smoke` pre-merge job runs three integration tests that
require real subprocess infrastructure (real Redis, real gunicorn workers,
real RQ queues):

- `tests/integration/test_multi_worker_concurrency.py`
- `tests/integration/test_redis_chaos.py`
- `tests/integration/test_real_multi_worker.py`

These tests catch regressions that mock-tier tests cannot — worker
coordination, lock contention across processes, Redis disconnect
recovery.  Moving them to pre-merge makes these regressions visible
at PR time instead of only in nightly runs.

## 2. Two-stage rollout

### Stage 4a — Informational (CURRENT)

- **Status**: Shipped 2026-04-23
- **Behaviour**: job runs on every `pull_request`, failures visible
  as red ✗ on PR, but the job is **NOT** in branch protection's
  required status checks.  PRs merge regardless of this job's outcome.
- **Purpose**: collect real PR-triggered signal without destabilising
  trunk velocity.  If a PR introduces a regression in these three
  files, the reviewer sees it; the merge decision is still theirs.
- **Triage**: Stage 4a failures follow the standard `triage.md`
  workflow (TEST_BUG / CODE_BUG / FLAKY_TEST) but do NOT automatically
  trigger revert.

### Stage 4b — Required (TARGET)

- **Status**: Blocked on stability thresholds (see §3).
- **Behaviour**: `real-infra-smoke` added to branch protection's
  required status checks.  PRs cannot merge if this job is red.
- **Action to promote**: a one-line branch protection change on
  GitHub (no workflow YAML edit, since Stage 4a already uses the
  final job name).

## 3. Promotion criteria (Stage 4a → Stage 4b)

All three conditions SHALL be met over a **20-day × 60-run window**,
where runs are sourced from `.github/workflows/measure-stability.yml`
nightly artifacts:

| Condition | Threshold | Math |
| :--- | :--- | :--- |
| Pass rate | **100%** (0 failures in 60 runs) | 1 failure = 98.3%, writing "99%" would be mathematically deceptive |
| p95 wall time | **< 180 s** per file | Keeps pre-merge total under a 10-minute timeout |
| No open flakiness | All root causes triaged + resolved | Filed in `openspec/changes/fix-<slug>/` |

The 100% threshold is **deliberate**.  A 60-run window admits only
`0/60` or `1/60` outcomes (100% or 98.3%).  Writing "≥ 99%" appears
to tolerate occasional failure but in fact still requires zero — a
misleading policy.

### 3.1 Relaxing to 99%

If a future change wants to tolerate 1 failure per window, it SHALL
first expand the rolling window to **≥ 100 runs** (e.g., 34 days ×
3 files = 102 runs, so 101/102 = 99.02%).  Merely relabelling the
60-run threshold from 100% to 99% without expanding the sample is
forbidden — it would create a 0-run gap where `99%` rounds to `100%`
requirements.

## 4. Measurement source

`.github/workflows/measure-stability.yml` runs nightly at 02:30 UTC
and uploads `stability-results.jsonl` as a 90-day-retention artifact.
`docs/real_infra_stability_report.md` is the human-readable rolling
summary; it is regenerated at each promotion decision and committed
to the upgrade PR for reviewer audit.

**Local burn-in supplements**: `scripts/measure_real_infra_stability.py`
may be run locally to produce supplementary evidence (e.g., pre-flight
confidence before CI data accumulates).  Local burn-in is recorded
under `artifacts/stability-local/` and in `docs/real_infra_stability_report.md`
§ "Local Pre-Filter" section.  It is NOT a substitute for CI data for
promotion purposes, because:

1. **Time diversity**: local consecutive runs share machine/network state.
2. **Auditability**: CI artifacts are URL-referenceable by reviewers;
   local artifacts are not.

## 5. Post-promotion revert trigger

After Stage 4b lands, the job SHALL be auto-reverted (via PR revert
merged within 24 hours) when:

- **7-day rolling flaky rate > 1%**, where **flaky** = runs that went
  red → green on rerun without code changes

When reverted, each identified flakiness root cause SHALL spawn
a `fix-<slug>` OpenSpec change before re-promotion is attempted.

## 6. Historical log

| Date | Stage | Action | Evidence |
| :--- | :--- | :--- | :--- |
| 2026-04-23 | 4a | `real-infra-smoke` job added to `backend-tests.yml` (informational only) | commit `<hash>` |
| *TBD* | 4b | Promote to required check | stability report snapshot, CI window summary |
