# Archive: wip-rq-worker-chunks-cleanup

## Change Summary

Two independent changes bundled for review economy. **Part B** implements the missing `execute_wip_detail_job` RQ worker (new `wip_query_job_service.py`) and registers the `"wip-detail"` job type so WIP detail queries at/above the L3 row threshold (200,000) — which were already being routed by `wip_routes.api_detail` via `enqueue_job_dynamic("wip-detail")` — actually execute async instead of silently falling through to sync via the `(None, "Unknown job type")` stub. The worker acquires `heavy_query_slot` around the Oracle phase only (progress 15→90), writes results to a new `wip_dataset` parquet spool, and ships inert (app.py import deferred to stress-soak sign-off). **Part C** deletes the deprecated, zero-caller `merge_chunks()` function from `batch_query_engine.py` (its surviving sibling `merge_chunks_to_spool()` and the shared exception classes stay).

## Final Behavior

- `enqueue_job_dynamic("wip-detail")` now resolves the registered worker instead of returning `(None, "Unknown job type")`. WIP detail queries with row count ≥ 200,000 and Redis available return HTTP 202 + pollable `query_id` (previously fell through to sync unconditionally).
- Worker is inert at merge: activation = uncomment the `app.py` import line + deploy `mes-dashboard-wip-worker.service`.
- `merge_chunks()` in `batch_query_engine.py` is deleted. `merge_chunks_to_spool`, `MergeChunksMaxRowsExceeded`, `ChunkSchemaMismatch` are preserved.
- `spool_routes._ALLOWED_NAMESPACES` includes `"wip_dataset"`.
- Sync fallback path (below-L3 / Redis-down / COUNT-error) is unchanged.

## Final Contracts Updated

| contract | version | change |
|---|---|---|
| contracts/api/api-contract.md | 1.26.0 | wip_dataset namespace added to spool allowlist; 202 added to WIP detail endpoint; WipDetailJobAccepted Tier-B schema; wip_routes.py added to Type-B list; compat note §10 |
| contracts/env/env-contract.md | 1.0.22 | WIP_WORKER_QUEUE / WIP_JOB_TIMEOUT_SECONDS / WIP_SPOOL_TTL added |
| contracts/env/env.schema.json | — | 3 WIP vars with type + default |
| contracts/ci/ci-gate-contract.md | 1.3.33 | wip-rq-worker-chunks-cleanup compat note |
| contracts/CHANGELOG.md | — | api 1.26.0, env 1.0.22, ci 1.3.33 entries |

## Final Tests Added / Updated

| file | nature |
|---|---|
| tests/test_wip_query_job_service.py (new, 11 tests) | AC-4 no-Oracle-at-enqueue, AC-6 merge_chunks absent, registration, slot placement, progress sequence, complete_job ordering |
| tests/test_batch_query_engine.py::TestMergeChunksAbsentFromSource (new, 3 tests) | ast.parse() absence proof; merge_chunks_to_spool + exception class guard |
| tests/test_job_registry.py | count 11→12; "wip-detail" asserted |
| tests/test_query_cost_policy.py | wip_query_job_service in _APPROVED_CALLERS |
| tests/test_spool_routes.py | wip_dataset in parametrized list + standalone assertion |
| tests/integration/test_wip_rowcount_rq_routing.py | AC-2 (202+spool), AC-3 (sync unchanged), AC-5 (redis-down + COUNT-error fail-open), AC-7 xfail(strict=True) |
| tests/integration/test_rq_semaphore_wiring.py::TestWipDetailConcurrencyCap | AC-8 slot wiring + fault release |
| tests/stress/test_wip_worker_stress.py (new, 2 tests) | N=20 burst (enters==exits==20, zero leak); mixed-fault (16 complete / 4 fault, exits=20) |

**Full suite result:** 132 passed, 1 xfailed (AC-7 camelCase gap, `xfail(strict=True)`)

## Final CI/CD Gates

- Tier 1 (pre-merge): lint, contract-validate, unit-mock-integration, response-shape-validate — all pass
- Tier 3 nightly: `pytest tests/integration/test_wip_worker_integration.py --run-integration-real`
- Tier 4 weekly: stress burst + soak
- Tier 5 manual (before activation): `stress-soak-report.md` sign-off — 3 gates: real-Redis peak-cap ≤ 3, AC-7 camelCase assembly, WIP soak endpoint

## Production Reality Findings

1. **Thread-safety bug in stress tests (stress-soak-engineer):** original N=20 stub applied `patch.object()` inside concurrent thread functions → concurrent context-manager restore races caused ~19/20 workers to see unpatched Oracle functions and raise `oracledb DPY-3001`. Fixed by moving all patches to test-method level via `monkeypatch.setattr` before thread launch. This pattern was already promoted to CLAUDE.md/test-discipline.md from rq-semaphore-wiring — confirmed again here.
2. **AC-7 camelCase gap (backend-engineer):** worker spool writes raw Oracle column names (LOTID, WIP_STATUS); sync path returns camelCase dict (lotId, wipStatus). Assembly layer not implemented in this change. Marked `xfail(strict=True)` — will become a real failure (not a pass) if an assembly layer were accidentally added without removing the xfail. Must resolve before activation.
3. **tier-floor-override required (pre-commit hook):** openapi regen touched `tests/contract/samples/post_auth_login.json` etc., triggering the `auth/login/logout` surface scanner. Override recorded in audit.yml with rationale (false-positive; no auth code modified).
4. **ci-gates.md queue name drift (qa-reviewer):** activation runbook steps 3-4 had `"wip-query"` instead of `"wip-detail-query"`. Fixed by qa-reviewer finding before close.

## Lessons Promoted to Standards

**Promoted (Candidate B):**
- **Target:** `CLAUDE.md` §Test coverage discipline + `docs/architecture/test-discipline.md` (new section)
- **Rule:** Cross-change spec gaps (async vs sync column-name parity etc.) must be marked `xfail(strict=True)` not plain `xfail` or `skip`. `strict=True` converts the test into a tripwire: CI fails (`XPASS`) if the gap is accidentally closed without removing the marker. Remove the decorator when the assembly layer is implemented.
- **Evidence:** `tests/integration/test_wip_rowcount_rq_routing.py::TestAsyncRowSchemaMatchesSyncPath`; qa-reviewer.yml §ac-summary
- **Schema bump:** none

**Not promoted (Candidate A — tier-floor-override false-positive from openapi regen):**
- Reason: existing tier-floor-override guidance already covers false-positives from surface scanners; audit.yml is the sufficient per-change record. One-off elaboration, not a new durable rule.

## Follow-up Work

| item | owner | gate |
|---|---|---|
| AC-7: camelCase assembly layer (Oracle → camelCase column mapping in async result path) | backend-engineer | stress-soak-report.md §Gate 2 — before activation |
| Real-Redis peak-cap validation (peak ≤ 3 concurrent WIP slots) | stress-soak-engineer | stress-soak-report.md §Gate 1 — before activation |
| DBA Oracle session headroom confirmation (1 conn/slot, not 2) | DBA / stress-soak-engineer | stress-soak-report.md §Gate 3 |
| Add POST /api/wip/detail to test_soak_workload.py _TRAFFIC_ENDPOINTS | stress-soak-engineer | post-activation Gate 3 |
| rq_monitor_service._QUEUE_NAMES: add "wip-detail-query" when activating | backend-engineer | ci-gates.md §Promotion Policy step 4 |

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.
