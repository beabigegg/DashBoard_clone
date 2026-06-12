# Change Classification

## Change Types
- primary: refactor (startup/caching architecture: daemon-thread → RQ unification), business-logic-change (spool TTL 2h→20h for two services)
- secondary: ci-cd-change (integration tests for gunicorn startup + RQ warmup paths), performance/caching

## Risk Level
- high

Rationale: touches `app.py` startup orchestration (gunicorn preload/fork-safety), the shared `spool_warmup_scheduler.py` `_WARMUP_JOBS` registry consumed by reject/yield_alert/hold/resource_dataset, and cache freshness semantics. A regression can silently fall back to Oracle on every query, double-run prewarms, or serve stale data.

## Impact Radius
- cross-module

Touches: two DuckDB cache services, shared warmup scheduler, app.py startup, spool TTL handling, and RQ worker/queue infra.

## Tier
- 1

## Architecture Review Required
- yes
- reason: Module-boundary change (daemon thread → RQ job model), startup/data-flow change in `app.py` under gunicorn preload-app fork safety, shared `_WARMUP_JOBS` registry modification affecting 4 existing datasets, and cache-freshness decision (20h TTL vs daily DuckDB refresh keyed by `loaded_at == today`). Operational risk trade-offs must be decided in `design.md` before implementation.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | captured in change-request.md Known Context |
| proposal.md | no | no user-facing behavior decision |
| spec.md | no | internal infra change |
| design.md | yes | Architecture Review Required = yes; spec-architect must record RQ-vs-daemon decision, fork-safety, _WARMUP_JOBS extension, TTL-scoping |
| qa-report.md | no | use agent-log unless blocking findings |
| regression-report.md | no | use agent-log unless blocking findings |
| visual-review-report.md | no | no UI output change |
| monkey-test-report.md | no | no new interactive surface |
| stress-soak-report.md | no | promote only if soak produces durable evidence |

## Required Contracts
- API: none (no endpoint or payload change)
- CSS/UI: none
- Env: `contracts/env/env-contract.md` — conditional: if 20h TTL introduced as env var, add key + default-value pin test; if hardcoded constant, add contract note only
- Data shape: none (parquet column schema unchanged)
- Business logic: `contracts/business/business-rules.md` — spool TTL freshness rule (20h aligned to daily DuckDB refresh) for resource_history + downtime_analysis; version entry to `contracts/CHANGELOG.md`
- CI/CD: `contracts/ci/ci-gate-contract.md` — only if new integration/soak gates added

## Required Tests
- unit: TTL resolves to 20h for resource_history + downtime_analysis only; global `CACHE_TTL_DATASET` and other datasets unchanged; `_WARMUP_JOBS` contains downtime_analysis entry; `loaded_at == today` refresh logic
- contract: default-value pin test if TTL becomes env var; business-rules TTL rule presence
- integration: gunicorn startup no longer launches daemon-thread prewarm; RQ warmup enqueued and executes for both services; multi-worker leader-lock prevents duplicate Oracle prewarm; first query before warmup completes falls back to Oracle; next query after daily DuckDB refresh reads fresh data
- E2E: none required; existing E2E tests must remain green as regression guard
- visual: none
- data-boundary: none
- resilience: RQ worker absent → Oracle fallback, no crash; metadata-TTL expiry while parquet persists → reader resolves
- fuzz/monkey: none
- stress: none pre-merge
- soak: daily-refresh + 20h-TTL boundary consideration — document in test-plan; run only if soak gate applies

## Required Agents
- spec-architect — write `design.md` before implementation-planner
- implementation-planner — execution packet after design + contracts + tests are known
- backend-engineer — implement scheduler extension, TTL change, remove daemon threads, add downtime-analysis warmup
- contract-reviewer — verify contracts and CHANGELOG
- qa-reviewer — release readiness decision (always last)

## Inferred Acceptance Criteria
- AC-1: At gunicorn startup, resource-history and downtime-analysis DuckDB prewarm are enqueued and executed via RQ jobs; no daemon-thread `start_duckdb_prewarm()` calls remain in `app.py`.
- AC-2: Three-month prewarm runs at startup and refreshes once daily, with DuckDB cache keyed by `loaded_at == today`.
- AC-3: downtime-analysis has an RQ spool warmup entry registered in `_WARMUP_JOBS` (previously absent).
- AC-4: Spool TTL for resource_history and downtime_analysis is 20h; global `CACHE_TTL_DATASET` and other datasets (hold, reject, yield_alert) are unchanged.
- AC-5: After the daily DuckDB refresh, the next query reads newly refreshed data (20h TTL ensures freshness post-refresh).
- AC-6: Under multiple gunicorn workers, warmup executes exactly once (leader/file-lock honored); no duplicate concurrent Oracle prewarms.
- AC-7: If RQ worker is unavailable at first query, query falls back to Oracle without error; parquet files persisting past metadata-TTL expiry remain readable.

## Tasks Not Applicable
- not-applicable: 2.1, 2.2, 2.4, 3.4, 4.2, 5.1, 5.2

## Clarifications or Assumptions
- No public API endpoint or payload shape changes; first-query Oracle fallback is pre-existing and explicitly accepted.
- Parquet column schema unchanged → no schema-breaking parquet cleanup required on deploy.
- Open decision for spec-architect: whether 20h TTL and RQ-warmup toggle are env vars or per-service hardcoded constants.

## Context Manifest Draft

### Affected Surfaces
- Spool/DuckDB caching architecture (resource_history, downtime_analysis)
- Shared spool warmup scheduler (_WARMUP_JOBS registry)
- Application startup orchestration (gunicorn preload/fork)
- RQ worker / queue infrastructure
- Env / business contracts (TTL semantics)

### Allowed Paths
- specs/changes/unify-duckdb-prewarm-rq/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/app.py
- src/mes_dashboard/core/spool_warmup_scheduler.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/services/resource_history_duckdb_cache.py
- src/mes_dashboard/services/downtime_analysis_duckdb_cache.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/config/settings.py
- src/mes_dashboard/config/constants.py
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/CHANGELOG.md
- contracts/ci/ci-gate-contract.md
- docs/adr/0004-gunicorn-preload-app-fork-safety.md
- docs/cache-strategy.md
- tests/integration/test_preload_fork_safety.py
- tests/integration/_multi_worker_harness.py
- tests/integration/conftest.py
- tests/test_env_contract.py

### Agent Work Packets

#### spec-architect
- specs/changes/unify-duckdb-prewarm-rq/
- specs/context/project-map.md
- src/mes_dashboard/app.py
- src/mes_dashboard/core/spool_warmup_scheduler.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/services/resource_history_duckdb_cache.py
- src/mes_dashboard/services/downtime_analysis_duckdb_cache.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/config/constants.py
- docs/adr/0004-gunicorn-preload-app-fork-safety.md
- docs/cache-strategy.md

#### implementation-planner
- specs/changes/unify-duckdb-prewarm-rq/
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md

#### backend-engineer
- specs/changes/unify-duckdb-prewarm-rq/
- src/mes_dashboard/app.py
- src/mes_dashboard/core/spool_warmup_scheduler.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/services/resource_history_duckdb_cache.py
- src/mes_dashboard/services/downtime_analysis_duckdb_cache.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/config/constants.py
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/CHANGELOG.md
- tests/integration/test_preload_fork_safety.py
- tests/integration/_multi_worker_harness.py
- tests/integration/conftest.py
- tests/test_env_contract.py

#### contract-reviewer
- specs/changes/unify-duckdb-prewarm-rq/
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/CHANGELOG.md
- contracts/ci/ci-gate-contract.md

#### qa-reviewer
- specs/changes/unify-duckdb-prewarm-rq/
- src/mes_dashboard/app.py
- src/mes_dashboard/core/spool_warmup_scheduler.py
- tests/integration/test_preload_fork_safety.py
- tests/integration/_multi_worker_harness.py

## Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - tests/ (resource_history + downtime_analysis cache unit test files)
  reason: services directory in project-map.md truncated at cap=50; exact test filenames for per-service cache unit tests not deterministically confirmed by index.
  status: pending
