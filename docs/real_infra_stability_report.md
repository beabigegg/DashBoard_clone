# Real-Infra Test Stability Report

This report tracks the rolling pass rate and wall-clock performance of
real-infrastructure integration tests.  It is updated weekly from artifact
data produced by the `measure-stability` GitHub Actions workflow.

---

## Gate Upgrade Criteria (Phase 4 trigger)

A test target is eligible for promotion to a required pre-merge check when
**all three** conditions are met over a **20-day × 3-runs/night = 60-run window**:

| Condition | Threshold | Notes |
| :--- | :--- | :--- |
| Pass rate | **100%** (0 failures in 60 runs) | A single failure = 98.3%; writing "99%" would be mathematically deceptive |
| p95 wall time | **< 180 s** | Ensures the pre-merge job stays within a 10-minute timeout slot |
| No open flakiness issues | All flakiness root causes triaged and resolved | Filed under `openspec/changes/harden-real-infra-test-coverage/` |

If a target passes but p95 > 180 s, fix the performance before promoting.
If pass rate < 100%, open a `fix-<slug>` OpenSpec change before re-measuring.

Relaxing the pass-rate threshold to 99% requires expanding the window to
≥ 100 runs first (≥ 34 nights of 3-run data); see design.md §D6 for the math.

---

## Weekly Summary Table

<!-- Replace placeholder rows with real data as runs accumulate. -->

| Week | Target | Runs | Pass rate | Mean wall (s) | p95 wall (s) | Notes |
| :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| 2026-Wxx | multi_worker | — | —% | — | — | Measurement not yet started |
| 2026-Wxx | redis_chaos | — | —% | — | — | Measurement not yet started |
| 2026-Wxx | real_multi_worker | — | —% | — | — | Measurement not yet started |

---

## Rolling 20-Day Pass Rate

| Target | Window start | Window end | Total runs | Failures | Pass rate | Gate-eligible? |
| :--- | :--- | :--- | ---: | ---: | ---: | :--- |
| multi_worker | — | — | — | — | — | Pending data |
| redis_chaos | — | — | — | — | — | Pending data |
| real_multi_worker | — | — | — | — | — | Pending data |

---

## Per-Run Flakiness Log

Record individual failures here as they occur.  Each entry feeds the
Phase 4 triage process.

| Date (UTC) | Target | Run # | Exit code | Failure summary | Root cause | Status |
| :--- | :--- | ---: | ---: | :--- | :--- | :--- |
| *(no failures yet)* | | | | | | |

---

## How to Update This Report

1. Download the `stability-results-<N>.jsonl` artifact from the
   `measure-stability` GitHub Actions run.
2. Append it to the local `stability-results.jsonl` file:
   ```bash
   cat stability-results-<N>.jsonl >> stability-results.jsonl
   ```
3. Recompute the weekly table and rolling window using:
   ```bash
   python scripts/measure_real_infra_stability.py --tests multi_worker,redis_chaos,real_multi_worker --runs 0
   ```
   *(runs=0 prints summary from existing JSONL without running new tests — **not yet implemented**, placeholder for Phase 4)*
4. Paste the updated numbers into the tables above and commit.
