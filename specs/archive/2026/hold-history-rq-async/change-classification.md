---
change-id: hold-history-rq-async
classifier-version: 1
---

# Change Classification

## Change Types
- primary: `feature-add` (new async query execution path for `POST /api/hold-history/query`)
- secondary: `api-only-change` (new 202 async branch + job-status contract), `env-change` (4 new `HOLD_*` vars), `ci-cd-change` (new RQ queue + systemd worker unit + worker-related gates)

## Lane
- feature

## Risk Level
- medium

Rationale: Additive, threshold-gated change (`HOLD_ASYNC_ENABLED` + `HOLD_ASYNC_DAY_THRESHOLD`) following a proven pattern already shipped twice (Phase 3-A downtime, production-history). Short-range queries keep the synchronous 200 path unchanged, limiting blast radius. Introduces a new RQ queue + worker (concurrency, fork-safety, memory-guard surface) and wraps a BatchQueryEngine row-count chunking path (per-chunk pct milestones — genuine difference from 3-A's date-range chunking). Not `high`: no auth/payments/migration, no breaking change, established rollback (feature flag off → sync behavior).

## Impact Radius
- cross-module

Spans backend service + route (hold_history_service / hold_history_routes), shared job registry, new worker, frontend hold-history app, env config, and deploy/CI. Contained to the hold-history feature plus shared async infrastructure already in place.

## Tier
- 2

## Architecture Review Required
- no
- reason: Architecture for this async migration pattern is already decided in `docs/dynamic-rq-migration-plan.md` with canonical pattern from Phase 1/2/3-A and ADRs 0003/0006. The only non-obvious point (row-count chunking with per-chunk pct milestones, ADR-0003 exclusion NOT applying) is a known bounded deviation that implementation-planner can capture. No new ADR warranted.

## Required Artifacts

Always required: `change-request.md`, `change-classification.md`, `implementation-plan.md`, `test-plan.md`, `ci-gates.md`, `tasks.yml`, `context-manifest.md`

## Optional Artifacts (default: no — set yes only with explicit reason)

| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Sync-only baseline is well understood; captured inline in implementation-plan |
| proposal.md | no | Product decision already made (migration plan Phase 3-B) |
| spec.md | no | Behavior fully specified by established 3-A pattern |
| design.md | no | Architecture pre-decided; reference migration plan + ADR-0003/0006 |
| qa-report.md | no | Routine pass/fail in agent-log/qa-reviewer.yml; promote only on blocking findings |
| regression-report.md | no | No existing-behavior change to sync path; regression evidence fits test-plan + agent-log |
| visual-review-report.md | no | Progress bar reuses existing AsyncQueryProgress.vue already reviewed in 3-A |
| monkey-test-report.md | no | Not applicable to this scope |
| stress-soak-report.md | no | Reuse existing test_async_job_stress.py; record results in agent-log |

## Required Contracts
- API: `contracts/api/api-contract.md` + `contracts/api/api-inventory.md` — document 202 async response on POST /api/hold-history/query
- CSS/UI: none — reuses existing AsyncQueryProgress.vue; no new CSS layer
- Env: `contracts/env/env-contract.md` + `.env.example` — 4 new HOLD_* vars with pinned defaults
- Data shape: conditional — promote to required only if async result envelope differs from sync payload
- Business logic: none — threshold gating is operational config, not a domain rule
- CI/CD: `contracts/ci/ci-gate-contract.md` — new hold-history-query RQ queue + systemd worker unit

## Required Tests
- unit: hold_query_job_service worker fn (per-chunk pct milestones, no mutation of execute_primary_query()); route 202/200 threshold branch; env-var default pinning (monkeypatch.setattr for module-level constants)
- contract: API contract test for 202 response; env-contract default-value tests for 4 HOLD_* vars
- integration: tests/integration/test_hold_history_rq_async.py (mirror test_downtime_rq_async.py); row-count chunk boundary + per-chunk pct progression
- E2E: extend hold-history Playwright spec — long-range → progress bar → correct result; short-range → 200 sync unchanged
- visual: covered by existing AsyncQueryProgress.test.js; add hold-history assertion only if rendering context differs
- data-boundary: async result row-count parity vs sync path for identical query; malformed/empty handling
- resilience: Redis-down / job-failure fallback; job-abandon-on-unload
- fuzz/monkey: not required
- stress: consideration — reuse tests/stress/test_async_job_stress.py (not pre-merge per test-layer governance)
- soak: consideration only — existing weekly test_soak_workload.py covers

## Required Agents
- `implementation-planner`
- `backend-engineer`
- `frontend-engineer`
- `contract-reviewer`
- `test-strategist`
- `ci-cd-gatekeeper`
- `qa-reviewer`

## Inferred Acceptance Criteria
- AC-1: When a hold-history query's date range ≥ `HOLD_ASYNC_DAY_THRESHOLD` (default 90 days) AND `HOLD_ASYNC_ENABLED` is true, `POST /api/hold-history/query` returns HTTP 202 with an async job handle.
- AC-2: When the date range < threshold (or `HOLD_ASYNC_ENABLED` is false), the endpoint returns HTTP 200 synchronously with the existing payload shape unchanged (short-range UX identical to today).
- AC-3: The async worker fn in `hold_query_job_service.py` wraps existing `execute_primary_query()` without modifying it, and produces a result identical to the synchronous path for the same query (row parity).
- AC-4: Progress milestones fire per row-count chunk, advancing through the 5→15→60→90→100 pct envelope as chunks complete.
- AC-5: The hold-history frontend renders the existing `AsyncQueryProgress` component during a long-range async query and displays the correct final result on completion.
- AC-6: The 4 new `HOLD_*` env vars are documented in `env-contract.md` and `.env.example` with pinned default values, and env-contract tests assert those defaults.
- AC-7: A new `hold-history-query` RQ queue and systemd worker unit are registered via `register_job_type()` / `rq_worker_preload` and covered by CI worker gates.
- AC-8: On Redis/job failure, the async path degrades safely without corrupting the synchronous path; `cdd-kit validate` passes.

## Tasks Not Applicable
- not-applicable: 1.3 (no design.md / architecture review — pattern pre-decided)

## Clarifications or Assumptions
1. Assumption: async result envelope is identical to sync payload (worker wraps execute_primary_query()). If it differs, data-shape contract becomes required.
2. Assumption: ADR-0003's row-count chunking exclusion is specific to downtime's cross-row reductions and does NOT apply to hold-history; worker may use row-count chunking with per-chunk milestones.
3. Assumption: HOLD_ASYNC_DAY_THRESHOLD default is 90 days (per migration plan Phase 3-B).
4. CER-001 filed: services/ truncated in project-map; implementation-planner must read hold_history_service.py to verify execute_primary_query() signature before planning milestone placement.
