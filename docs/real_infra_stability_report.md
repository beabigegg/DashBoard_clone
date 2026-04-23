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

## Local Pre-Filter

> **Status**: `local pre-filter` is a supplementary go/no-go signal, NOT a
> substitute for the 20-day × 60-run CI window used for Stage 4b promotion
> (see `docs/ci_real_infra_gate_policy.md` §4).  It is recorded here so
> that reviewers can audit the Stage 4a decision against real data.
>
> Local burn-in compresses 60 runs per target into a single session and
> therefore lacks cross-day / cross-runner variance.  A 100% pass rate
> locally is a **necessary but not sufficient** signal for gate promotion.

### 2026-04-22 session — Stage 4a go/no-go signal

- **Script**: `scripts/measure_real_infra_stability.py --tests multi_worker,redis_chaos,real_multi_worker --runs 60`
- **Artifact**: `artifacts/stability-local/stability-20260422T010200Z.jsonl` (180 records)
- **Log**: `artifacts/stability-local/stability-20260422T010200Z.log`
- **Environment**: mes-dashboard conda env, local redis-server, no Oracle (real_multi_worker uses gunicorn + RQ only)
- **Wall-clock span**: 01:02:54 UTC → 03:24:27 UTC (2h 22m total)

| Target | Runs | Pass | Failures | Mean wall (s) | p95 wall (s) | Max wall (s) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| multi_worker | 60 | 60 | 0 | 59.8 | 72.5 | 73.8 |
| redis_chaos | 60 | 60 | 0 | 45.9 | 55.6 | 60.9 |
| real_multi_worker | 60 | 60 | 0 | 36.7 | 44.7 | 49.1 |
| **Aggregate** | **180** | **180** | **0** | — | — | — |

**Verdict**: green — Stage 4a land is go.  900 test assertions across 180
runs, zero failures; every target's p95 is well below the 180s gate
threshold.  This result is **sufficient** to land `real-infra-smoke` as
an informational PR check (Stage 4a).  It is **not sufficient** for Stage
4b promotion, which still requires the 20-day × 60-run CI window.

**Limitations explicitly acknowledged**:
1. Single-session burn-in does not exercise cross-day variance (package
   mirror state, Docker Hub rate limits, weekend vs weekday runner load)
2. Local dev environment has warmer caches and a known-good Redis install
   path — it does not match CI's `apt-get install redis-server` cold path
3. No Oracle container ran in this session; `test_real_multi_worker.py`
   does not use Oracle, so this is scope-correct, but any future target
   that touches Oracle would need a separate session with the fault-injection
   container stack

### 2026-04-23 session — cross-day burn-in (morning peak)

- **Script**: `scripts/measure_real_infra_stability.py --tests multi_worker,redis_chaos,real_multi_worker --runs 60`
- **Artifact**: `artifacts/stability-local/stability-20260423T000218Z.jsonl` (180 records)
- **Log**: `artifacts/stability-local/stability-20260423T000218Z.log`
- **Environment**: mes-dashboard conda env, local redis-server, no Oracle
- **Wall-clock span**: 00:03:26 UTC → 02:26:39 UTC (2h 23m total)
- **Timing rationale**: ~23 h after the 2026-04-22 01:02 UTC session, during
  local morning peak load, to exercise cross-day host variance (different
  system load, network state, cache warmth)

| Target | Runs | Pass | Failures | Mean wall (s) | p95 wall (s) | Max wall (s) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| multi_worker | 60 | 60 | 0 | 63.0 | 75.0 | 79.9 |
| redis_chaos | 60 | 60 | 0 | 45.1 | 55.9 | 63.5 |
| real_multi_worker | 60 | 60 | 0 | 36.2 | 43.2 | 52.5 |
| **Aggregate** | **180** | **180** | **0** | — | — | — |

**Drift vs 2026-04-22 session** (Δ p95 vs previous session):

| Target | 2026-04-22 p95 | 2026-04-23 p95 | Δ |
| :--- | ---: | ---: | ---: |
| multi_worker | 72.5 s | 75.0 s | +2.5 s |
| redis_chaos | 55.6 s | 55.9 s | +0.3 s |
| real_multi_worker | 44.7 s | 43.2 s | −1.5 s |

**Verdict**: green — two back-to-back 180-run sessions across different
times of day both land 100% pass.  Combined local signal now stands at
**360/360 runs** (1,800 test assertions) with zero failures and every
target's p95 remains well below the 180 s gate threshold (worst case
multi_worker 75 s = 42% of budget).  Cross-day drift is in the noise
floor.

**Still-insufficient-for-Stage-4b reasons unchanged**: local burn-in
remains a go-no-go pre-filter, not a substitute for the CI 20-day × 60-run
window (see `docs/ci_real_infra_gate_policy.md` §4).  The 2026-04-22
CI `measure-stability` scheduled run did fire (Day 1 of the rolling
window), so CI data accumulation is on schedule.

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
