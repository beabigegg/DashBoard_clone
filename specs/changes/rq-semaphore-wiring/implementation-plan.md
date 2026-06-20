---
change-id: rq-semaphore-wiring
schema-version: 0.1.0
last-changed: 2026-06-20
---

# Implementation Plan: rq-semaphore-wiring

## Objective
Bound Oracle-phase concurrency across the heavy RQ workers by wiring the existing
`global_concurrency` semaphore around — and only around — the Oracle fetch inside three
`execute_*_job` workers (query-tool, hold, resource), via a new exception-safe
`@contextmanager` helper `heavy_query_slot(owner)`. Reject is already wired at the cache
layer and gets no job-level acquire. No new env var, no response/job-output change,
flag-off paths byte-for-byte identical. Realizes ADR 0011 and closes the wiring gap in
service-patterns.md §RQ Worker Concurrency Gate.

## Execution Scope

### In Scope
- Add `heavy_query_slot(owner)` `@contextmanager` to `global_concurrency.py` (the only new code there).
- Wrap the Oracle phase (between pct=15 and pct=90 emits) in `execute_query_tool_job`,
  `execute_hold_history_query_job`, `execute_resource_history_query_job`.
- Unit tests (new `tests/test_rq_semaphore_wiring.py`; extend `tests/test_global_concurrency.py`).
- Integration test `tests/integration/test_rq_semaphore_wiring.py` (Tier-3, `integration_real`/`multi_worker`).
- Stress test `tests/stress/test_rq_semaphore_stress.py` (Tier-4, `stress`) + `stress-soak-report.md`.
- Documentation correction to service-patterns.md §RQ Worker Concurrency Gate (idiom + reject status).

### Out of Scope
- Any job-level acquire in `execute_reject_query_job` — already wired internally in
  `reject_dataset_cache.execute_primary_query` (design D3); adding one double-counts and violates AC-1/AC-6.
- Bracketing `ensure_canonical_spool` in hold/resource — explicitly deferred (design D3, test-plan Out of Scope).
- Any new env var or env-contract default change (AC-7).
- `heavy_query_telemetry.py` writes / acquire-latency metrics (design D5).
- Any change to `acquire_heavy_query_slot` / `release_heavy_query_slot` signatures or fail-open behavior.
- Refactoring worker structure, progress emits, or job-result shapes beyond the acquire/release wrap.
- DBA headroom validation for resource 2-connection fan-out (operational, not code).

## Required Changes
| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | core semaphore | Add `heavy_query_slot(owner)` `@contextmanager` to `global_concurrency.py`; import `contextmanager` | backend-engineer |
| IP-2 | query-tool worker | Wrap Oracle-phase `result = get_*(...)` dispatch in `with heavy_query_slot(owner):` | backend-engineer |
| IP-3 | hold worker | Wrap `result = execute_primary_query(...)` in `with heavy_query_slot(owner):` | backend-engineer |
| IP-4 | resource worker | Wrap `result = execute_primary_query(...)` in `with heavy_query_slot(owner):` (base+OEE fan-out; document only) | backend-engineer |
| IP-5 | docs | Correct service-patterns.md §RQ Worker Concurrency Gate idiom + reject-wired status (doc-only) | backend-engineer |
| IP-6 | unit tests | Write `tests/test_rq_semaphore_wiring.py` + `TestHeavyQuerySlotCM` in `tests/test_global_concurrency.py` BEFORE IP-2..IP-4 | test-strategist |
| IP-7 | integration test | Write `tests/integration/test_rq_semaphore_wiring.py` (N=8 across job types) | stress-soak-engineer |
| IP-8 | stress test + report | Write `tests/stress/test_rq_semaphore_stress.py` (N=20 burst) + `stress-soak-report.md` | stress-soak-engineer |
| IP-9 | verification | Run bounded test ladder via `cdd-kit test run`; emit `test-evidence.yml` | backend-engineer |

## Source Artifact Pointers
| source | relevant pointer | used for |
|---|---|---|
| design.md | D1 (Oracle-phase scope), D2 (bool not CM; add helper), D3 (reject/spool deferrals), D4 (progress parity), D5 (no telemetry) | implementation constraints |
| design.md | Affected Components table | per-worker wrap locations |
| change-classification.md | AC-1..AC-7 | acceptance criteria |
| test-plan.md | AC→test mapping table; Notes | test files/names and authoring rules |
| ci-gates.md | Required Gates table; Promotion/Rollback Policy | verification commands; promotion preconditions |
| docs/adr/0011-... | acquire "inside RQ worker around the Oracle fetch" | scope conformance |
| docs/architecture/service-patterns.md | §RQ Worker Concurrency Gate (lines 131-147) | stale doc to correct (IP-5) |
| reference impl | `production_history_service.py:522-530` | acquire/try/finally/release idiom |

## File-Level Plan
| path or glob | action | notes |
|---|---|---|
| `src/mes_dashboard/core/global_concurrency.py` | edit | Add `from contextlib import contextmanager`; add `@contextmanager def heavy_query_slot(owner)`: `acquired = acquire_heavy_query_slot(owner)`; `try: yield acquired`; `finally: if acquired: release_heavy_query_slot(owner)`. Existing `acquire`(85-122)/`release`(125-133) unchanged. |
| `src/mes_dashboard/services/query_tool_service.py` | edit | `execute_query_tool_job` (2783-2906): wrap the `result = get_*(...)` dispatch block (~2820-2860, between pct=15 emit @2811 and pct=90 emit @2868) in `with heavy_query_slot(owner):`. `owner` is the existing job param. Single phase, no re-acquire (D3). |
| `src/mes_dashboard/services/hold_query_job_service.py` | edit | `execute_hold_history_query_job` (94-171): wrap `result = execute_primary_query(...)` (~131) in `with heavy_query_slot(owner):`. Leave `ensure_canonical_spool` (148-153) and `complete_job` OUTSIDE the slot (D3). |
| `src/mes_dashboard/services/resource_query_job_service.py` | edit | `execute_resource_history_query_job` (94-184): wrap `result = execute_primary_query(...)` (~137) in `with heavy_query_slot(owner):`. Do NOT forward `owner` into `execute_primary_query`. base+OEE ThreadPool fan-out = 2 Oracle conns under 1 slot — deliberate; document in a code comment, do NOT change. Leave `ensure_canonical_spool` (159-160) OUTSIDE. |
| `src/mes_dashboard/services/reject_query_job_service.py` | none | NO job-level acquire. `execute_primary_query` (called @172) already acquires/releases internally. Read-only reference for AST-absence test. |
| `docs/architecture/service-patterns.md` | edit | Lines 137-142: change idiom from `with acquire_heavy_query_slot():` to `with heavy_query_slot(owner):`; update gap statement so reject is listed as wired at cache layer, only the three workers needed job-level wiring. Doc-only, not a contract change. |
| `tests/test_global_concurrency.py` | edit | Add `TestHeavyQuerySlotCM` (do not duplicate `TestAcquireHeavyQuerySlot`). |
| `tests/test_rq_semaphore_wiring.py` | create | Per-worker wiring, flag-off parity, reject AST-absence, exception-release. |
| `tests/integration/test_rq_semaphore_wiring.py` | create | N=8 multi-worker peak-sampling. |
| `tests/stress/test_rq_semaphore_stress.py` | create | N=20 burst, `@pytest.mark.stress`. |

## Contract Updates
- API: none (no endpoint or response-shape change).
- CSS/UI: none.
- Env: none — AC-7; env-contract.md confirmed read-only, no new key.
- Data shape: none (job result schemas unchanged).
- Business logic: none in this plan — contract-reviewer owns the candidate concurrency-bound
  rule decision; if added it is reviewed separately, not authored here.
- CI/CD: none — ci-gates.md confirms all three new test files fall under existing gate discovery
  (no workflow YAML change).

## Test Execution Plan
| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | `tests/integration/test_rq_semaphore_wiring.py::TestConcurrencyCap::test_peak_oracle_concurrent_bounded` | peak overlap ≤ HEAVY_QUERY_MAX_CONCURRENT (3) |
| AC-2 | `tests/integration/test_rq_semaphore_wiring.py::TestConcurrencyCap::test_all_jobs_complete_no_deadlock` | all N=8 reach terminal state, no stall |
| AC-3 | `tests/integration/test_rq_semaphore_wiring.py::TestConcurrencyCap::test_semaphore_fully_released_after_run` | `get_active_slot_count()` == 0 post-run |
| AC-4 | `tests/test_rq_semaphore_wiring.py::TestHeavyQuerySlotCM::test_slot_released_on_oracle_exception` | release called once on raise |
| AC-4 | `tests/test_rq_semaphore_wiring.py::TestHeavyQuerySlotCM::test_next_job_acquires_after_exception` | next acquire succeeds |
| AC-5 | `tests/test_rq_semaphore_wiring.py::TestFlagOffParity::test_query_tool_flag_off_no_slot_acquire` | acquire never called flag-off |
| AC-5 | `tests/test_rq_semaphore_wiring.py::TestFlagOffParity::test_hold_flag_off_no_slot_acquire` | acquire never called flag-off |
| AC-5 | `tests/test_rq_semaphore_wiring.py::TestFlagOffParity::test_resource_flag_off_no_slot_acquire` | acquire never called flag-off |
| AC-6 | `tests/test_rq_semaphore_wiring.py::TestPerWorkerWiring::test_query_tool_slot_acquired_once` | exactly one acquire, around Oracle phase |
| AC-6 | `tests/test_rq_semaphore_wiring.py::TestPerWorkerWiring::test_hold_slot_acquired_once` | exactly one acquire |
| AC-6 | `tests/test_rq_semaphore_wiring.py::TestPerWorkerWiring::test_resource_slot_acquired_once` | exactly one acquire |
| AC-6 | `tests/test_rq_semaphore_wiring.py::TestRejectWorkerAbsence::test_reject_job_has_no_job_level_acquire` | AST walk: no `acquire_heavy_query_slot` call in `execute_reject_query_job` |
| AC-6 | `tests/test_global_concurrency.py::TestHeavyQuerySlotCM` | yields bool; release guarded by `acquired` on fail-open |
| AC-7 | `tests/test_env_contract.py` | env key count unchanged |
| AC-1..AC-3 (burst) | `tests/stress/test_rq_semaphore_stress.py::TestSemaphoreStress::test_burst_peak_bounded_no_leak` | N=20 cap held, no leak (Tier-4) |

Required test phases (floor): collect, targeted, changed-area. Add contract (env-contract assertion),
quality, and full per their triggers. Evidence is produced via `cdd-kit test run`; the gate validates
`test-evidence.yml`. Selector entrypoint: `cdd-kit test select rq-semaphore-wiring --json`. Tier-3/Tier-4
gates run post-merge on schedule (ci-gates.md); not pre-merge blockers.

### Execution order (TDD)
1. IP-6 (write unit tests — must fail first; helper/import not yet present).
2. IP-1 (CM helper) — required before IP-2..IP-4 so tests can import `heavy_query_slot`.
3. IP-2, IP-3, IP-4 (worker wiring) — tests flip green.
4. IP-5 (doc correction).
5. IP-7, IP-8 (integration + stress + report).
6. IP-9 (run ladder, emit evidence).

## Handoff Constraints
- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- `acquire_heavy_query_slot()` returns a **bool**, not a context manager. Use `heavy_query_slot(owner)`
  (IP-1) or the bare `acquire`/try/finally/`release` idiom from `production_history_service.py:522-530`.
  `release` MUST be guarded by `acquired` so fail-open never double-releases.
- Do NOT add an acquire to `execute_reject_query_job`.
- Do NOT change flag-off path behavior or `progress_callback` ordering.
- Do NOT add any env var.
- Slot scope is the Oracle phase only (between pct=15 and pct=90), never job-global.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.

## Known Risks
- service-patterns.md §RQ Worker Concurrency Gate currently shows the non-working
  `with acquire_heavy_query_slot():` form and wrongly lists reject as unwired; IP-5 must correct both
  in the same change to keep the doc truthful.
- Resource worker holds 2 Oracle connections under 1 slot (base+OEE ThreadPool, `max_workers=2`).
  Deliberate; DBA headroom must be validated as `HEAVY_QUERY_MAX_CONCURRENT × 2 + overhead` against
  worker `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` before any resource flag-on (ADR 0011 Consequences; ci-gates Promotion Policy). Do not change behavior here.
- Reject slot owner is `sync:<pid>:<lock_owner>` (pre-async naming relic); harmless for counting,
  misleading in logs — note for a future cleanup, not this change.
- Flag-off parity tests must use `monkeypatch.setattr` on the module-level flag constant (frozen at
  import), not `os.environ` (test-discipline.md; test-plan Notes).
- CI has no Redis: acquire fails open to `True`. Unit tests must patch the CM/acquire rather than rely
  on real Redis; integration peak-sampling patches `heavy_query_slot` to record entry/exit (test-plan Notes).
