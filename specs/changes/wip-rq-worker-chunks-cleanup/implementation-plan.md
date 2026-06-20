---
change-id: wip-rq-worker-chunks-cleanup
schema-version: 0.1.0
last-changed: 2026-06-20
---

# Implementation Plan: wip-rq-worker-chunks-cleanup

## Objective
Make the WIP detail query path actually run async at/above the L3 row threshold (200,000) by implementing the missing `execute_wip_detail_job` RQ worker and registering the `"wip-detail"` job type, with `acquire_heavy_query_slot` wired inside the worker (Oracle phase only). Result delivery uses a new `wip_dataset` parquet spool so the existing 202 -> poll -> fetch contract holds with row-schema parity to the sync path. Independently, delete the deprecated zero-caller `merge_chunks()` from `batch_query_engine.py`. The worker ships **inert** (not imported in `app.py`) until the pre-production gate signs off.

## Execution Scope

### In Scope
- New `src/mes_dashboard/services/wip_query_job_service.py`: `execute_wip_detail_job` + enqueue-helper + module-bottom `register_job_type("wip-detail", ...)`.
- `wip_service.py`: add a spool-materializing primary-query helper the worker calls (`execute_primary_query`-style); sync paged path untouched.
- `spool_routes.py`: add `"wip_dataset"` to `_ALLOWED_NAMESPACES`.
- Delete `merge_chunks()` from `batch_query_engine.py` (def + docstring refs at L22/L29) and its non-spool tests.
- New `deploy/mes-dashboard-wip-worker.service` systemd unit.
- API + env contract updates (10 items in contract-reviewer.yml) + `openapi.json` regen + CHANGELOG.
- Unit/integration/resilience/stress-stub tests per test-plan.md.
- `app.py` activation import is written as a deferred/commented step (NOT live) — see Non-goals and ci-gates.md Promotion Policy.

### Out of Scope
- Frontend / Playwright app changes beyond the lightweight 202->poll happy-path already mapped (e2e-resilience-engineer).
- WIP filter options, WIP search-index incremental/full-rebuild paths.
- Sync-path internals (`get_wip_detail` paged-dict logic), L1/L2 routing thresholds, spool TTL value tuning.
- `merge_chunks_to_spool`, `MergeChunksMaxRowsExceeded`, `ChunkSchemaMismatch` and their tests.

## Non-goals (do NOT do)
- Do NOT change the sync `get_wip_detail` paged-dict return shape or any sync-path internals.
- Do NOT introduce a routing flag (`WIP_DETAIL_USE_RQ` / `WIP_ASYNC_ENABLED`). Per design D1, routing is gated solely by `is_async_available()` + `classify_query_cost(domain="wip", ...)` already present in `wip_routes.py`. Only operational tuning vars are added.
- Do NOT delete `merge_chunks_to_spool` (L777), `MergeChunksMaxRowsExceeded` (L601), or `ChunkSchemaMismatch` (L614) from `batch_query_engine.py`. Their spool tests stay.
- Do NOT add the live `app.py` import for `wip_query_job_service` — activation is gated on `stress-soak-report.md` sign-off (ci-gates.md Promotion Policy step 2).
- Do NOT change the route routing logic or the 202 shape in `wip_routes.api_detail` — both are already present (L321-379). Only remove the misleading comment at L367-370.

## Required Changes
| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | tests | Write failing unit/absence tests first (see Execution order) | backend-engineer |
| IP-2 | service | Delete `merge_chunks()` from `batch_query_engine.py`; remove its non-spool tests | backend-engineer |
| IP-3 | worker | Create `wip_query_job_service.py`: `execute_wip_detail_job` + slot wiring + `register_job_type("wip-detail")` | backend-engineer |
| IP-4 | service | Add `wip_service` spool-materializing primary-query helper (confirm name/return) | backend-engineer |
| IP-5 | spool | Materialize `wip_dataset` parquet; add `"wip_dataset"` to `spool_routes._ALLOWED_NAMESPACES` | backend-engineer |
| IP-6 | app wiring | Document `app.py` import as activation step (commented/deferred, NOT live) | backend-engineer |
| IP-7 | deploy | Create `deploy/mes-dashboard-wip-worker.service` systemd unit | backend-engineer |
| IP-8 | API contract | api-contract.md (5 edits) + regen `openapi.json` | backend-engineer |
| IP-9 | env contract | env-contract.md + env.schema.json + CHANGELOG.md | backend-engineer |
| IP-10 | integration | Extend `test_wip_rowcount_rq_routing.py` (202, schema parity, fail-open) | backend-engineer / e2e-resilience-engineer |
| IP-11 | stress stub | Create `tests/stress/test_wip_worker_stress.py` reference stub | stress-soak-engineer |
| IP-12 | evidence | Run bounded ladder; record `test-evidence.yml` | backend-engineer |

## Source Artifact Pointers
| source | relevant pointer | used for |
|---|---|---|
| design.md | D1 (no routing flag), D2 (slot placement), D3 (canonical spool / `wip_dataset`), D4 (merge_chunks blast radius), D5 (progress milestones 5/15/90/100), D6 (registration site) | implementation constraints |
| design.md | Open Risks: spool schema parity (AC-7) | the pre-implementation risk to resolve below |
| test-plan.md | AC->test mapping table; New/Existing test files; Notes (xfail, ast.parse) | tests to write/run |
| ci-gates.md | Required Gates table; Promotion Policy; Pre-Production Manual Gate | verification + activation sequencing |
| agent-log/contract-reviewer.yml | items 1-10 + default values | contract edits |
| change-classification.md | AC-1..AC-8 | acceptance criteria |
| `hold_query_job_service.py` | L96-194 (canonical Type-B: slot 15->90, complete_job outside slot, module-bottom register) | template for IP-3 |
| `job_registry.py` | `JobTypeConfig` L26-49 (`job_type, queue_name, worker_fn, ..., always_async=False`); `register_job_type` L63-69 | IP-3 registration |
| `wip_routes.py` | L321-379 routing + 202 + enqueue stub (already present); comment L367-370 to delete | IP-3/route confirmation |
| `batch_query_engine.py` | `merge_chunks` def L632, docstring refs L22/L29, deprecation L642-652; KEEP L601/L614/L777 | IP-2 |

## File-Level Plan
| path or glob | action | notes |
|---|---|---|
| `src/mes_dashboard/services/wip_query_job_service.py` | create | `execute_wip_detail_job(*, job_id, owner, **query_params)`; slot wraps Oracle phase only (pct 15->90); `complete_job`/spool write OUTSIDE slot; module-bottom `register_job_type(JobTypeConfig(job_type="wip-detail", queue_name=WIP_WORKER_QUEUE, worker_fn=execute_wip_detail_job, timeout_seconds=WIP_JOB_TIMEOUT_SECONDS, ttl_seconds=..., always_async=False))`. No `WIP_*_USE_RQ` flag. Slot acquired here only — never at request time (AC-4). |
| `src/mes_dashboard/services/wip_service.py` | edit (add fn) | Add spool-materializing primary-query helper the worker calls (D2/D3). Reconcile summary+lots shape — see Open Risk. Sync `get_wip_detail` (L1542) and `count_wip_rows` (L4205) UNCHANGED. |
| `src/mes_dashboard/services/batch_query_engine.py` | edit (delete) | Remove `merge_chunks()` (def L632 + body through ~L770) and docstring import refs L22/L29. KEEP `merge_chunks_to_spool` (L777), `MergeChunksMaxRowsExceeded` (L601), `ChunkSchemaMismatch` (L614). |
| `src/mes_dashboard/routes/spool_routes.py` | edit | Add `"wip_dataset"` to `_ALLOWED_NAMESPACES`. |
| `src/mes_dashboard/routes/wip_routes.py` | edit (comment only) | Delete misleading "not registered" comment L367-370. No routing/202-shape change. |
| `src/mes_dashboard/app.py` | edit (deferred/documented) | Activation import line written as commented placeholder + note pointing to ci-gates Promotion Policy. NOT live in this change. |
| `deploy/mes-dashboard-wip-worker.service` | create | systemd unit running `rq worker $WIP_WORKER_QUEUE`; mirror sibling hold/resource worker units. |
| `contracts/api/api-contract.md` | edit | items 1-5 below. |
| `contracts/api/openapi.json` | regen | `cdd-kit openapi export` after api-contract edits (CI gate). |
| `contracts/env/env-contract.md` | edit | item 7 below. |
| `contracts/env/env.schema.json` | edit | item 8 below. |
| `contracts/CHANGELOG.md` | edit | item 9: api 1.25.1->1.26.0 (minor), env 1.0.21->1.0.22 (patch). |
| `tests/test_wip_query_job_service.py` | create | AC-4 (no Oracle at enqueue; slot wraps Oracle phase 15->90), AC-6 (merge_chunks absent from new module). NOTE: test-plan.md / ci-gates.md also reference the name `test_wip_worker_semaphore.py` for the same surface — confirm final filename with test-strategist; one canonical file. |
| `tests/test_batch_query_engine.py` | edit | Delete `TestMergeChunks` (lines ~345-495) + `merge_chunks` import L11; add `test_merge_chunks_absent_from_source` via `ast.parse()`. KEEP spool tests. |
| `tests/test_job_registry.py` | edit | Bump registered-job-type count +1; assert `"wip-detail"` present (use `importlib.reload()` after clearing registry to re-run module-level `register_job_type`). |
| `tests/test_query_cost_policy.py` | edit | Add `wip_query_job_service` stem to `_APPROVED_CALLERS`. |
| `tests/test_spool_routes.py` | edit | Add `"wip_dataset"` to the parametrized allowed-namespaces list (same-PR rule). |
| `tests/integration/test_wip_rowcount_rq_routing.py` | edit | Extend per test-plan.md: 202 path + spool readable (AC-2), schema parity vs sync `lots[0]` keys (AC-3/AC-7), Redis-down fail-open (AC-5). |
| `tests/integration/test_rq_semaphore_wiring.py` | edit | Add `test_wip_detail_slot_respects_concurrency_cap` mirroring `test_peak_oracle_concurrent_bounded` (AC-8). |
| `tests/stress/test_wip_worker_stress.py` | create | Stress stub for pre-production gate (Tier 4); see ci-gates.md Pre-Production Manual Gate. |

## Contract Updates
Reference agent-log/contract-reviewer.yml items 1-10 (do not restate full prose). Defaults backend-engineer must confirm: `WIP_WORKER_QUEUE="wip-detail-query"`, `WIP_JOB_TIMEOUT_SECONDS=1800`, `WIP_SPOOL_TTL=72000`.

- API: items 1-6 — add `wip_dataset` to `/api/spool/{namespace}/{query_id}.parquet` allowlist; add `202` to WIP detail endpoint rows error column; add `WipDetailJobAccepted` Tier-B schema; add `wip_routes.py` to Section 7 Type-B list; add Section 10 compatibility note; regen `openapi.json`.
- CSS/UI: none.
- Env: items 7-9 — add `## Async Worker — WIP Detail Query` section (3 vars) to env-contract.md; add same 3 vars to env.schema.json (with default; queue/ttl/timeout are tuning vars, no enum); add version bumps to CHANGELOG.md.
- Data shape: none (AC-7 is flag-only parity assertion, no data-shape contract change — but the async assembled response MUST be shape-equivalent to sync; see Open Risk).
- Business logic: none (L3 semantics unchanged).
- CI/CD: no workflow YAML change (auto-discovered); ci-gate-contract.md compat note appended at schema 1.3.33 per ci-gates.md.

## Test Execution Plan
| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | tests/test_job_registry.py | `"wip-detail"` registered; count +1 |
| AC-2 | tests/integration/test_wip_rowcount_rq_routing.py | above-L3 -> 202 + job_id; spool parquet retrievable |
| AC-3 | tests/integration/test_wip_rowcount_rq_routing.py | below-L3 sync 200 unchanged |
| AC-4 | tests/test_wip_query_job_service.py | no Oracle at enqueue; slot only inside worker, wraps pct 15->90 |
| AC-5 | tests/integration/test_wip_rowcount_rq_routing.py | Redis-down/COUNT-error fails open to sync, never 503 |
| AC-6 | tests/test_batch_query_engine.py | `merge_chunks` absent via `ast.parse()`; spool fns intact |
| AC-6 | tests/test_wip_query_job_service.py | new module does not reference `merge_chunks` |
| AC-7 | tests/integration/test_wip_rowcount_rq_routing.py | async spool columns == sync `lots[0]` keys (Open Risk: `xfail(strict=True)` until reconciled) |
| AC-7 | tests/test_spool_routes.py | `wip_dataset` passes namespace validation |
| AC-8 | tests/integration/test_rq_semaphore_wiring.py | peak concurrency <= cap; no slot leak |
| AC-8 | tests/stress/test_wip_worker_stress.py | (Tier 4) slot contention bounded; stub for pre-prod gate |
| (registry guard) | tests/test_query_cost_policy.py | `wip_query_job_service` in `_APPROVED_CALLERS` |

Required phase floor: collect, targeted, changed-area (commands in test-plan.md Test Execution Ladder). Contract phase applies (api+env edited): `cdd-kit validate --contracts`. Quality phase: `ruff check .`. Full ladder authority: test-plan.md + ci-gates.md (do not restate here).

## Execution Order (TDD)
1. **IP-1** Write failing tests: `tests/test_wip_query_job_service.py` (AC-4 slot/no-Oracle, AC-6 module absence), `test_job_registry.py` count+`"wip-detail"`, `test_query_cost_policy.py` `_APPROVED_CALLERS`, `test_spool_routes.py` `wip_dataset` param, `test_batch_query_engine.py` `test_merge_chunks_absent_from_source` (ast.parse).
2. **IP-2** Delete `merge_chunks()` from `batch_query_engine.py` + its non-spool tests -> AC-6 tests pass immediately.
3. **IP-3** Create `wip_query_job_service.py` (`execute_wip_detail_job`, slot wiring D2, register D6) -> AC-1/AC-4/AC-8 unit pass.
4. **IP-4** Add `wip_service` spool-materializing primary-query helper (confirm exact name/return at source). **Resolve Open Risk first.**
5. **IP-5** Spool write -> `wip_dataset` parquet + register_spool_file + add namespace to `_ALLOWED_NAMESPACES`.
6. **IP-6** Document `app.py` import as deferred activation step (NOT live).
7. **IP-7** Create `deploy/mes-dashboard-wip-worker.service`.
8. **IP-8** API contract edits (items 1-5) + regen `openapi.json`.
9. **IP-9** Env contract + schema + CHANGELOG (items 7-9).
10. **IP-10** Integration tests: 202 path, schema parity, fail-open.
11. **IP-11** Stress stub `tests/stress/test_wip_worker_stress.py`.
12. **IP-12** Run bounded ladder; record `test-evidence.yml`.

## Open Risk to Resolve Before Implementation (AC-7)
The sync `get_wip_detail` returns a single dict carrying both a `summary` (totals/qty/status breakdown — see `wip_service.py` ~L978-1010) AND paged `lots` rows. A parquet spool can only carry the row set. Before writing the AC-7 schema-parity test green, **backend-engineer must confirm** whether the summary fields can be deterministically recomputed from the spooled parquet rows at async-result assembly time, OR must be carried as job metadata alongside the spool (`complete_job` extra fields). Until resolved, set `pytest.mark.xfail(strict=True)` on the schema-parity test (test-plan.md Notes). The async assembled response MUST end up shape-equivalent to the sync response (contract-reviewer item: flag-only, no data-shape contract change).

## Handoff Constraints
- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- The `app.py` activation import and worker deploy are gated on `stress-soak-report.md` sign-off — do not activate during this change.

## Known Risks
- DBA Oracle session headroom: new Oracle-bound worker adds to `HEAVY_QUERY_MAX_CONCURRENT` budget (one connection per slot, not two). Owned by stress-soak-report.md / ADR 0011.
- Test filename ambiguity: ci-gates.md/test-plan.md reference both `test_wip_query_job_service.py` and `test_wip_worker_semaphore.py` for the new unit surface. Pick ONE canonical file; confirm with test-strategist to avoid a split/duplicate unit file.
- `wip_dataset` namespace + parametrized spool-route test must land in the same PR (CLAUDE.md rule) — already in IP-1/IP-5.
- `register_job_type` module-level side-effect: registry-count test must use `importlib.reload()` (not `setattr`) to re-run registration (test-discipline.md).
- code-map.yml: read-hook now prefers `cdd-kit index query`; source ranges in this plan were validated via Grep extraction (line numbers may drift by a few lines as files are edited — treat as anchors, not exact offsets).
