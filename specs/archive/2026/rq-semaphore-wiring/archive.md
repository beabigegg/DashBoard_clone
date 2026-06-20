# Archive: rq-semaphore-wiring

## Change Summary

Added a `heavy_query_slot(owner)` context manager helper to `global_concurrency.py` and wired it into three RQ worker functions (`execute_query_tool_job`, `execute_hold_history_query_job`, `execute_resource_history_query_job`) around the Oracle-phase only. The semaphore was always present but never acquired by RQ workers — workers could bypass the `MAX_CONCURRENT=3` cap silently once their feature flag went live. Each wiring is guarded by the corresponding feature flag so the flag-off path is byte-for-byte identical (inert until flag-on). `execute_reject_query_job` is excluded because it acquires at the cache layer and adding a job-level acquire would double-count slots.

## Final Behavior

- `heavy_query_slot(owner)` contextmanager wraps `acquire_heavy_query_slot` / `release_heavy_query_slot` with exception-safe try/finally; `if acquired` guard ensures fail-open never double-releases.
- RQ workers for query-tool, hold, resource each enter the CM during the Oracle-phase only (between pct=15 and pct=90 milestones). `ensure_canonical_spool` and `complete_job` remain outside the slot.
- All wiring is flag-gated: `_QUERY_TOOL_CONCURRENCY_WIRED` (based on `QUERY_TOOL_USE_RQ`), `HOLD_ASYNC_ENABLED`, `RESOURCE_ASYNC_ENABLED`.
- At flag-off, the `nullcontext()` substitution means zero acquire/release calls — parity proven by unit tests.
- Resource worker fans base+OEE over `ThreadPoolExecutor(max_workers=2)` = 2 Oracle connections per slot; DBA headroom confirmation required before `RESOURCE_ASYNC_ENABLED` flag-on.

## Final Contracts Updated

- `contracts/business/business-rules.md`: ASYNC-15 added; 2 Decision Table rows; version 1.28.0 → 1.29.0
- `contracts/ci/ci-gate-contract.md`: gate-compatibility note (stress-soak-report.md required before flag promotion); version 1.3.31 → 1.3.32
- `contracts/env/env-contract.md`: no change (HEAVY_QUERY_MAX_CONCURRENT gap is follow-up debt)

## Final Tests Added / Updated

- `tests/test_global_concurrency.py::TestHeavyQuerySlotCM` — 5 tests: yields bool, fail-open yields False, releases on success/exception, no double-release
- `tests/test_rq_semaphore_wiring.py` — 12 tests: per-worker acquire/release, flag-off parity, exception slot release, AST absence proof for reject worker
- `tests/integration/test_rq_semaphore_wiring.py::TestConcurrencyCap` — 4 tests: N=8 peak≤3, no deadlock, no leak, fault-inject release
- `tests/stress/test_rq_semaphore_stress.py::TestSemaphoreStress` — 2 tests: N=20 burst (all complete, no leak), mixed-fault (17 success + 3 fault, full release)
- Full suite: 4899 passed, 0 failed

## Final CI/CD Gates

- Pre-merge (Tier 1): lint, contract-validate, unit-mock-integration, response-shape-validate
- Informational (Tier 3/4): nightly-integration (integration_real), stress-load (weekly), soak (weekly)
- Manual / pre-production: `stress-soak-report.md` must demonstrate `peak_concurrent ≤ 3`, no leak, no deadlock before any `*_USE_RQ` flag is promoted to on

## Production Reality Findings

- **Tier-floor-override required**: cdd-kit `.cdd/tier-policy.json` maxTier=0 rule triggered on "deadlock"/"query" keywords; resolved with `tier-floor-override` in tasks.yml frontmatter. Establishes Tier-1 convention for all future RQ worker flag-gated changes.
- **Test pollution risk (concurrent patch())**: integration tests initially used `patch()` inside threads, which races on module attribute restore and pollutes sibling test modules. Rewrote to `monkeypatch.setattr()` for all module-level attributes before thread launch — must be the pattern for all future threaded tests.
- **Reject worker sync naming relic**: `reject` uses `sync:<pid>:<lock_owner>` slot owner format (pre-async naming); cosmetically inconsistent but harmless for cap counting. Noted for future cleanup.

## Lessons Promoted to Standards

**A: Tier-floor-override — flag-gated concurrency wiring**
- Target: `CLAUDE.md` line (CDD Kit operations bullet) + `docs/cdd-kit-patterns.md` (flag-gated paragraph after zero-caller section)
- Rule: flag-gated concurrency wiring (all flags default-off) is a second valid `tier-floor-override` trigger; unlike zero-caller modules the override stands for the full flag-off period, not just until first caller lands
- Evidence: `agent-log/audit.yml` (tier-floor-override granted); `contracts/business/business-rules.md` ASYNC-15

**B: Threaded tests — monkeypatch before thread launch**
- Target: `docs/architecture/test-discipline.md` (new section "Threaded Tests — Apply All Monkeypatches Before Thread Launch") + `CLAUDE.md` line (Module-level constants bullet extended)
- Rule: all `monkeypatch.setattr()` calls must complete BEFORE threads are launched — `patch()`/`patch.object()` inside thread bodies causes concurrent attribute restore races that pollute sibling test modules
- Evidence: `agent-log/backend-engineer.yml` implementation-notes; confirmed failure in test-run `20260620-100337` (`test_hold_dataset_cache.py::test_long_range_triggers_engine` polluted by concurrent patch() restore race)

## Follow-up Work

- Add `HEAVY_QUERY_MAX_CONCURRENT` to `contracts/env/env-contract.md` with `enum` + `default: "3"` (follow-up change; identified by contract-reviewer)
- Resource worker: DBA headroom confirmation (`HEAVY_QUERY_MAX_CONCURRENT × 2 + overhead` connections within `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`) required before `RESOURCE_ASYNC_ENABLED` flag-on
- Real-Redis peak-cap test (`peak_concurrent ≤ 3` under actual Redis): mock tests prove wiring, real Redis proof required for flag-on (pre-production gate in `stress-soak-report.md`)
- Reject slot-owner naming relic (`sync:<pid>:<lock_owner>`) — cosmetic cleanup, no functional impact

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.
