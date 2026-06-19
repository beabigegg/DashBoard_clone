# CI/CD Gate Review

## Change ID
query-path-c-elimination-cleanup

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|---:|---|---|---|
| lint | 0 | yes | local pre-PR / push | `ruff check .` | — |
| contract-validate | 0 | yes | local pre-PR | `cdd-kit validate` | — |
| response-shape-validate | 1 | yes | push / PR | `cdd-kit validate --contracts` (via `contract-driven-gates.yml`) | — |
| unit-mock-integration | 1 | yes | push / PR | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` (via `backend-tests.yml` `unit-and-integration-tests` job) | junit XML |
| cdd-gate | 1 | yes | push / PR | `cdd-kit gate query-path-c-elimination-cleanup` | — |
| playwright-resilience | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/resilience/` (via `backend-tests.yml`) | playwright trace (7 days) |
| playwright-critical-journeys | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/query-tool.spec.js` (via existing critical-journeys gate) | playwright trace (7 days) |
| nightly-integration | 3 | yes (nightly) | schedule / dispatch | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` (via `backend-tests.yml` `nightly-integration-real` job) | test report (30 days) |
| stress-load | 4 | yes (weekly) | schedule / dispatch | `pytest tests/stress/ -m "stress or load"` (via `contract-driven-gates.yml` `scheduled-stress-soak` job) | stress-soak-report.md (90 days) |

## Gate-to-AC Traceability

| gate | acceptance criteria covered |
|---|---|
| lint | general code quality; no direct AC |
| contract-validate | AC-5 (env-contract removes 4 vars), AC-7 (QUERY_TOOL_USE_RQ default off pin), AC-6 (business-rules semaphore semantics) |
| response-shape-validate | AC-1 (202+job_id async-dispatch shape for query_tool), AC-3 (wip rowcount pre-check response shape) |
| unit-mock-integration | AC-1 (flag-on dispatch unit test — mock is_async_available=True + enqueue_query_job), AC-2 (flag-off inline path, query_tool_routes), AC-3 (wip sub-L3 inline; >= L3 routes to RQ unit), AC-4 (merge_chunks DeprecationWarning + backward-compat), AC-5 (4 vars absent from env.schema.json; routes use classify_query_cost), AC-6 (global_concurrency docstring/contract semantics), AC-7 (QUERY_TOOL_USE_RQ present in schema; default off), (registry: test_job_registry.py count 10→11 + "query-tool" in expected_types) |
| cdd-gate | cross-cutting: all tasks.yml done/skipped, test-evidence.yml present, ci-gates.md filled |
| playwright-resilience | AC-2 (flag-off behavior unchanged — Playwright query-tool.spec.js small-query path); AC-3 (sub-L3 WIP stays inline) |
| playwright-critical-journeys | AC-2 (flag-off behavior unchanged end-to-end); AC-3 (WIP hold pages sub-L3 inline) |
| nightly-integration | AC-1 (flag-on oversized query → 202+job_id, no worker block — real Redis + RQ); AC-2 (flag-off parity vs pre-change); AC-3 (>= L3 routes to RQ, real Oracle row count); AC-5 (4 removed vars absent in integration env); AC-8 (worker-blocking-elimination: oversized query path never blocks gunicorn) |
| stress-load | AC-8 (RQ Oracle concurrency <= HEAVY_QUERY_MAX_CONCURRENT semaphore bound; no gunicorn worker starvation under load; no wip COUNT(*) contention) |

## CI/CD Workflow Changes

### What is auto-discovered (no workflow YAML edits required)

All new test files for this change fall within existing gate discovery scopes:

- `tests/contract/test_env_query_tool_flag.py` (and related env-pin tests) — auto-discovered by `unit-mock-integration` gate (pytest root collection from `tests/`).
- `tests/test_batch_query_engine.py` (DeprecationWarning assertion additions) — existing file, auto-discovered.
- `tests/test_job_registry.py` (count bump 10→11 + "query-tool" set addition) — existing file, auto-discovered.
- `tests/test_query_cost_policy.py` (drop `_DEPRECATED_THRESHOLD_VARS` assertions) — existing file, auto-discovered.
- `tests/integration/test_query_tool_rq_async.py` (new — flag on/off parity, worker-blocking-elimination) — auto-discovered by `nightly-integration` gate (`integration_real` marker, skipped pre-merge).
- `tests/stress/test_query_tool_stress.py` (new — RQ Oracle-concurrency bound, no worker starvation) — auto-discovered by `stress-load` gate (`stress` marker).
- `tests/e2e/test_query_tool_e2e.py` (updates — small query inline, flag-off) — auto-discovered by existing e2e gate.
- `tests/e2e/test_wip_hold_pages_e2e.py` (updates — sub-L3 WIP inline) — auto-discovered by existing e2e gate.

### CI environment variable cleanup (workflow YAML change required)

The 4 removed env vars (`DOWNTIME_ASYNC_DAY_THRESHOLD`, `HOLD_ASYNC_DAY_THRESHOLD`, `RESOURCE_ASYNC_DAY_THRESHOLD`, `REJECT_ASYNC_DAY_THRESHOLD`) must be removed from any `env:` block in `.github/workflows/backend-tests.yml` and `.github/workflows/contract-driven-gates.yml` in the same PR as the source deletion.

Current audit: `backend-tests.yml` has one `env:` block under `unit-and-integration-tests` step (line 59) with `PORTAL_SPA_ENABLED: "true"` — none of the 4 vars are present there. `contract-driven-gates.yml` has no `env:` blocks setting those vars. **No workflow YAML `env:` removal is needed for this specific change.**

### New `QUERY_TOOL_USE_RQ` env var (workflow YAML — no action required)

`QUERY_TOOL_USE_RQ` defaults to `off` / `false`. CI workflows do not need to set it explicitly — gate runs verify the flag-off (default) path, which is the safe merge state.

### No new workflow files required

All new tests are auto-discovered by existing gate commands. No new `.github/workflows/*.yml` files are introduced by this change.

### Concurrency (existing, no change required)

The existing `contract-driven-gates.yml` and `backend-tests.yml` do not yet set `concurrency:` blocks. This change does not introduce new concurrent jobs and does not require a concurrency group change.

## Promotion Policy

### workflow

No new workflow files are introduced. All tests for this change are picked up by the existing `unit-and-integration-tests`, `nightly-integration-real`, and `scheduled-stress-soak` jobs. The `response-shape-validate` gate (Tier 1 required) and `unit-mock-integration` gate (Tier 1 required) must both be green before this PR is eligible to merge.

### promotion policy

- `nightly-integration` is already a Tier 3 required (nightly) gate; the new `tests/integration/test_query_tool_rq_async.py` is picked up immediately on the nightly run after merge. No promotion cycle required.
- `stress-load` is already Tier 4 weekly; the new `tests/stress/test_query_tool_stress.py` is picked up on the next weekly run. The `stress-soak-report.md` authored by stress-soak-engineer is required before promoting `QUERY_TOOL_USE_RQ` to `on` in production, but is **not** a pre-merge gate blocker (AC-8 is a production-readiness gate, not a merge-eligibility gate).
- Any new informational gate added in the future for this change surface must follow the standard Informational Gate Promotion Policy (20 calendar days / 60 runs / pass rate above threshold / failures triaged / runtime within limit / owner assigned).

## Rollback Policy

### rollback policy

**Flag-off rollback (query_tool Path C):**
1. Set `QUERY_TOOL_USE_RQ=off` (or unset — default is off). Reload or restart gunicorn. `QUERY_TOOL_USE_RQ` is resolved at route entry via `resolve_bool_flag`; no worker restart required if the flag is env-loaded (not module-level constant). Verify `query_tool_routes` falls through to the inline path.
2. If `QUERY_TOOL_USE_RQ` is implemented as a module-level constant (frozen at boot), a **full gunicorn restart** is required — `kill -HUP` reloads workers but not master environment.
3. The `query-tool` RQ worker can remain running; it simply receives no new jobs when the flag is off.

**wip rowcount pre-check rollback:**
No feature flag gates the wip COUNT(*) pre-check. Rollback is git revert of `wip_routes.py` and `wip_service.py`. The pre-check is fail-open (COUNT error → SYNC), so a degraded Oracle never makes WIP stricter than before this change.

**Env-var removal rollback:**
The 4 `*_ASYNC_DAY_THRESHOLD` vars were already inert at the point of this change (routing used `classify_query_cost`). Re-introduction requires a git revert of the source file changes, env-contract.md, env.schema.json, .env.example, and the contract tests. No operator env action is required; deployed `.env` files that still set removed vars silently ignore them.

**merge_chunks deprecation rollback:**
Additive only — the `@deprecated` marker and `DeprecationWarning` do not change behavior or break callers. Rollback (removing the marker) is a cosmetic git revert.

**No spool / parquet cleanup required:**
`query_tool_routes` has no persistent spool (see ci-gate-contract.md §material-part-consumption). No DuckDB parquet files are introduced by this change. Do NOT add parquet cleanup steps to this rollback.

**Tier 1 gate failure policy:**
If any Tier 1 required gate turns red after merge, the `main` branch is frozen for new PRs until repaired. A fix PR must pass all Tier 1 gates before merging to `main`.

## Artifact Retention

| artifact | retention |
|---|---|
| pytest / junit XML (unit-mock-integration) | 30 days |
| playwright traces (resilience, critical-journeys) | 7 days (30 days on failure) |
| nightly integration test report | 30 days |
| stress-soak-report.md (tests/stress/ output) | 90 days |
| hypothesis failure examples | 30 days |

## Merge Eligibility

**mergeable** when ALL of the following pass:

1. `lint` (`ruff check .`) — green locally and on PR push.
2. `contract-validate` (`cdd-kit validate`) — green.
3. `response-shape-validate` (`cdd-kit validate --contracts`) — green; confirms 202+job_id async shape and env-schema removal.
4. `unit-mock-integration` — green; confirms AC-1 through AC-7, registry count 10→11, DeprecationWarning, env-pin contract tests.
5. `cdd-gate` (`cdd-kit gate query-path-c-elimination-cleanup`) — green; confirms tasks.yml, test-evidence.yml, and this ci-gates.md are complete.
6. `playwright-resilience` and `playwright-critical-journeys` — green; confirms flag-off and sub-L3 inline path end-to-end.

**Informational / post-merge verification (does not block merge):**
- `nightly-integration` — first nightly run after merge; confirms AC-1/AC-2/AC-3/AC-8 against real Redis + RQ.
- `stress-load` — first weekly run after merge; confirms AC-8 Oracle concurrency bound and no worker starvation.
- `stress-soak-report.md` authored by stress-soak-engineer — required before promoting `QUERY_TOOL_USE_RQ` to `on` in production.

**Blocked conditions:**
- Any Tier 1 required gate red.
- `test_job_registry.py` count still 10 (IP-11 must update to 11 in same PR as IP-2).
- 4 removed env vars still present in `env.schema.json` (IP-7 must co-ship with IP-9/IP-10 and IP-11 contract tests — R4).
- `openapi.json` out of sync after api-contract.md edits (IP-9 co-ship constraint).

