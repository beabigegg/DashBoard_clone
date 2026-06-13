---
change-id: downtime-rq-async
classifier-version: 1
---

# Change Classification

## Change Types
- primary: `feature-add` (new RQ async query path for Downtime Analysis), `api-change` (new 202 async response on POST /api/downtime-analysis/query)
- secondary: `env-change` (4 new DOWNTIME_* vars), `ui-change` (AsyncQueryProgress integration in downtime-analysis App.vue), `ci-cd-change` (new downtime worker CI gate + deploy/systemd unit), `data-shape-change` (async job response shape; parquet spool parity)

## Lane
- feature

## Risk Level
- high

Rationale: introduces a new async execution path and a new long-running RQ worker process in front of an existing synchronous query, with a dual-path branch (sync vs async by day threshold). Touches a long-running job queue, parquet spool writes (two interdependent files — DA-11 atomic-validation rule), env-gated rollout, and deployment topology (new systemd service + gunicorn config). Parity between sync and async paths is a correctness-critical guarantee.

## Impact Radius
- cross-module

Spans route layer, new service/worker, job-registry dispatcher (Phase 2), frontend feature app + shared async-polling composable, env/api/ci contracts, and deploy. Confined to the downtime-analysis vertical plus shared async plumbing.

## Tier
- 1

high risk + cross-module maps to Tier 0–1; classifying at Tier 1 (cross-module, not system-wide, and built on already-delivered Phase 1/2 primitives rather than greenfield infrastructure).

## Architecture Review Required
- yes
- reason: Introduces a dual-path (sync/async) branch with a new long-running worker process, new deploy topology (systemd + gunicorn), two-parquet-spool atomic write ordering with pct milestones, and a rollback/feature-flag (DOWNTIME_ASYNC_ENABLED) decision. These are module-boundary, data-flow, operational-risk, and migration/rollback decisions that must be settled in `design.md` before implementation planning — especially the parity guarantee (AC-3) and ADR-0003 (no ROW_NUMBER chunking) interaction with the worker fn.

## Required Artifacts

Always required: `change-request.md`, `change-classification.md`, `implementation-plan.md`, `test-plan.md`, `ci-gates.md`, `tasks.yml`, `context-manifest.md`

## Optional Artifacts (default: no — set yes only with explicit reason)

| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Existing sync behavior is well understood; captured inline in design.md |
| proposal.md | no | Migration is already decided (Phase 3-A) |
| spec.md | no | Behavior fully specified by AC-1..AC-7 |
| design.md | yes | Architecture Review Required = yes (dual-path branch, worker/deploy topology, parquet ordering, rollback flag, parity strategy) |
| qa-report.md | no | Routine pass/fail via agent-log unless blocking findings arise |
| regression-report.md | no | Track regression via test-plan + agent-log unless a regression is found |
| visual-review-report.md | no | AsyncQueryProgress is a pre-existing Phase-1 component |
| monkey-test-report.md | no | Not warranted at this scope |
| stress-soak-report.md | no | Default to agent-log pointer unless high-risk load/soak results surface |

## Required Contracts
- API: `contracts/api/api-contract.md` — document 202 async response (`{async: true, job_id, status_url}`) on POST /api/downtime-analysis/query; keep 200 sync path for short queries
- CSS/UI: none (AsyncQueryProgress is an existing shared component; no new CSS layer required)
- Env: `contracts/env/env-contract.md` — add DOWNTIME_ASYNC_ENABLED, DOWNTIME_ASYNC_DAY_THRESHOLD (default 30), DOWNTIME_WORKER_QUEUE, DOWNTIME_JOB_TIMEOUT_SECONDS with pinned defaults
- Data shape: `contracts/data/data-shape-contract.md` — async job response shape + parquet parity contract
- Business logic: `contracts/business/business-rules.md` — async threshold gate rule; cross-reference DA-11 and ADR-0003
- CI/CD: `contracts/ci/ci-gate-contract.md` — new downtime worker CI gate

## Required Tests
- unit: threshold-branch logic (sync vs async selection), env-var default pinning (monkeypatch.setattr, not setenv), `register_job_type()` registration via importlib.reload
- contract: api-contract 202/200 shapes; env-contract 4 vars with pinned default values; data-shape job response + parquet schema
- integration: `execute_downtime_query_job()` enqueue/dispatch via `enqueue_job_dynamic()`; spool write ordering + DA-11 atomic validation; check `pytestmark` before adding mock tests under tests/integration/
- E2E: long-range query → 202 → polling → progress bar render → results; cancel flow; short-range query → 200 sync
- visual: none new (reuse Phase-1 AsyncQueryProgress visuals)
- data-boundary: parity test — RQ worker fn vs sync path produce byte/row-identical base_events and job_bridge parquet (AC-3); pct milestone sequence 5→15→60→90→100
- resilience: worker startup sentinel, job timeout handling, cancel mid-job
- fuzz/monkey: none
- stress: consideration — concurrent long-running async jobs against downtime queue
- soak: consideration — long-running worker stability over extended job stream

## Required Agents
- `spec-architect` — writes `design.md`; required because Architecture Review = yes
- `implementation-planner` — turns design + contracts + tests into execution packet
- `backend-engineer` — new `downtime_query_job_service.py`, worker fn, route 202/200 branch, env wiring, job registry integration
- `frontend-engineer` — AsyncQueryProgress integration in downtime-analysis App.vue + useAsyncJobPolling
- `test-strategist` — parity tests, threshold tests, contract tests, AC→test mapping
- `contract-reviewer` — api/env/data/business/ci contract changes
- `ui-ux-reviewer` — async progress/cancel interaction and short-query unchanged UX (AC-5)
- `ci-cd-gatekeeper` — new downtime worker CI gate, deploy/systemd + gunicorn config
- `e2e-resilience-engineer` — worker startup/timeout/cancel resilience + long-range E2E flow
- `qa-reviewer` — release readiness, parity + rollback verification

## Inferred Acceptance Criteria
- AC-1: A query spanning ≥ DOWNTIME_ASYNC_DAY_THRESHOLD (default 30) days returns HTTP 202 with body `{async: true, job_id, status_url}`.
- AC-2: A query spanning < threshold returns HTTP 200 via the existing synchronous path with byte/row-identical data to current behavior (no regression).
- AC-3: A parity test proves the RQ worker fn `execute_downtime_query_job()` produces exactly the same `base_events` and `job_bridge` parquet data as the synchronous path.
- AC-4: env-contract adds DOWNTIME_ASYNC_ENABLED, DOWNTIME_ASYNC_DAY_THRESHOLD (default 30), DOWNTIME_WORKER_QUEUE, DOWNTIME_JOB_TIMEOUT_SECONDS with pinned defaults and passes `cdd-kit validate`.
- AC-5: Frontend long-range query renders AsyncQueryProgress with a working cancel action; short-range UI is unchanged.
- AC-6: The worker fn updates pct milestones in the documented sequence 5→15→60→90→100, and writes the two parquet spools (base_events, job_bridge) atomically per DA-11.
- AC-7: The downtime-query job is dispatched through the existing Phase-2 `enqueue_job_dynamic()` + `register_job_type()` registry, and a new downtime worker process/CI gate is provisioned with a verified startup sentinel.

## Tasks Not Applicable
- not-applicable: (none — all sections applicable; design review required so 1.3 applies)

## Clarifications or Assumptions
- Assumption: Phase 1 (AsyncQueryProgress.vue) and Phase 2 (job_registry / enqueue_job_dynamic / register_job_type) are DONE and stable.
- Assumption: DOWNTIME_ASYNC_ENABLED acts as rollback feature flag — disabling it must restore pure-sync behavior.
- Assumption: ADR-0003 applies — worker fn wraps existing single-segment `query_downtime_dataset_raw()` and must not reintroduce BatchQueryEngine ROW_NUMBER chunking.
- Note: stress/soak are flagged as consideration; promote to report only if high-risk load/soak results surface.

## Context Manifest Draft

### Affected Surfaces
- API route: downtime-analysis query (sync/async branch)
- New backend service + RQ worker fn (downtime-query queue)
- Job-registry dispatcher (Phase 2 plumbing)
- Frontend downtime-analysis app + shared async-polling composable
- Contracts: api, env, data, business, ci
- Deploy: new downtime worker systemd unit + gunicorn config

### Allowed Paths
- specs/changes/downtime-rq-async/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md
- src/mes_dashboard/routes/downtime_analysis_routes.py
- src/mes_dashboard/services/downtime_analysis_service.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/downtime_analysis_duckdb_cache.py
- src/mes_dashboard/services/downtime_query_job_service.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/workers/
- frontend/src/downtime-analysis/App.vue
- frontend/src/downtime-analysis/composables/
- frontend/src/shared-ui/components/AsyncQueryProgress.vue
- frontend/src/shared-composables/useAsyncJobPolling.ts
- docs/adr/0003-downtime-rowcount-chunking-exclusion.md
- docs/adr/0007-downtime-browser-duckdb-compute-relocation.md
- deploy/
- gunicorn.conf.py
- .env.example
- tests/test_downtime_analysis_service.py
- tests/integration/
- tests/e2e/test_downtime_analysis_e2e.py
- frontend/tests/playwright/downtime-analysis.spec.js

### Required Contracts
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md

### Required Tests
- tests/test_downtime_analysis_service.py
- tests/integration/
- tests/e2e/test_downtime_analysis_e2e.py
- frontend/tests/playwright/downtime-analysis.spec.js

### Agent Work Packets

#### spec-architect
- specs/changes/downtime-rq-async/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md
- docs/adr/0003-downtime-rowcount-chunking-exclusion.md
- docs/adr/0007-downtime-browser-duckdb-compute-relocation.md
- src/mes_dashboard/services/downtime_analysis_service.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/services/job_registry.py

#### implementation-planner
- specs/changes/downtime-rq-async/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md

#### backend-engineer
- specs/changes/downtime-rq-async/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- src/mes_dashboard/routes/downtime_analysis_routes.py
- src/mes_dashboard/services/downtime_analysis_service.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/downtime_analysis_duckdb_cache.py
- src/mes_dashboard/services/downtime_query_job_service.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/workers/
- .env.example
- tests/test_downtime_analysis_service.py
- tests/integration/

#### frontend-engineer
- specs/changes/downtime-rq-async/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- frontend/src/downtime-analysis/App.vue
- frontend/src/downtime-analysis/composables/
- frontend/src/shared-ui/components/AsyncQueryProgress.vue
- frontend/src/shared-composables/useAsyncJobPolling.ts
- frontend/tests/playwright/downtime-analysis.spec.js

#### test-strategist
- specs/changes/downtime-rq-async/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- src/mes_dashboard/services/downtime_query_job_service.py
- src/mes_dashboard/services/downtime_analysis_service.py
- tests/test_downtime_analysis_service.py
- tests/integration/
- tests/e2e/test_downtime_analysis_e2e.py
- frontend/tests/playwright/downtime-analysis.spec.js

#### contract-reviewer
- specs/changes/downtime-rq-async/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md

#### ui-ux-reviewer
- specs/changes/downtime-rq-async/
- frontend/src/downtime-analysis/App.vue
- frontend/src/shared-ui/components/AsyncQueryProgress.vue
- frontend/src/shared-composables/useAsyncJobPolling.ts

#### ci-cd-gatekeeper
- specs/changes/downtime-rq-async/
- contracts/ci/ci-gate-contract.md
- contracts/env/env-contract.md
- deploy/
- gunicorn.conf.py
- .env.example

#### e2e-resilience-engineer
- specs/changes/downtime-rq-async/
- contracts/api/api-contract.md
- src/mes_dashboard/services/downtime_query_job_service.py
- src/mes_dashboard/workers/
- tests/integration/
- tests/e2e/test_downtime_analysis_e2e.py
- frontend/tests/playwright/downtime-analysis.spec.js

#### qa-reviewer
- specs/changes/downtime-rq-async/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md

### Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - frontend/src/downtime-analysis/composables/
  reason: project-map truncates the downtime-analysis composables directory; frontend-engineer needs the exact composable that owns query dispatch to wire the 202/polling branch
  status: pending
- request-id: CER-002
  requested_paths:
    - deploy/
    - gunicorn.conf.py
  reason: ci-cd-gatekeeper needs the existing worker systemd units and gunicorn config as template for the new downtime-query worker
  status: pending
