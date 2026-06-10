# Change Classification

## Change Types
- primary: `bug-fix`, `performance-fix`
- secondary: `refactor` (cache-key strategy / dual-path consolidation), `business-logic-change` (cache correctness behavior, not user-visible output)

## Risk Level
- high

Rationale: touches the resource-history caching core (Redis spool key strategy, background warmup, multi-worker startup) — a documented silent-failure zone (namespace mismatch, startup lock, schema-version-driven parquet invalidation). Wrong key strategy produces zero cache benefit silently and/or `BinderException`/schema-mismatch on stale parquet, affecting production response time directly.

## Impact Radius
- module-level (resource-history caching + warmup), with a cross-module touchpoint on the shared spool/warmup infrastructure (`core/spool_warmup_scheduler.py`, `core/query_spool_store.py`, `core/redis_df_store.py`). Bounded to one feature's read path; no other page's cache logic changes.

## Tier
- 1

Rationale: high risk + module-level with cross-module infrastructure touchpoint. Classifying upward from medium/cross-module boundary because of documented silent-failure history and production impact.

## Architecture Review Required
- yes
- reason: Non-obvious cache-key strategy decision (System A filter-inclusive vs System B canonical, granularity removal, whether to deprecate System A, view-result cache TTL, schema_version bump and stale-parquet invalidation/rollback). Open Questions in the request (TTL value, System-A deprecation scope) confirm design decisions are pending.

## Required Artifacts

Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)

| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | captured in change-request §Known Context |
| proposal.md | no | no product-facing decision; technical scope is clear |
| spec.md | no | API response shape unchanged |
| design.md | yes | architecture review required; cache-key strategy + System-A/B consolidation decision |
| qa-report.md | no | promote only if QA finds blocking/approved-with-risk items |
| regression-report.md | no | use agent-log pointer unless pre-existing failure must be excluded |
| visual-review-report.md | no | no frontend/UI change |
| monkey-test-report.md | no | not applicable |
| stress-soak-report.md | no | not pre-merge per project governance |

## Required Contracts
- API: read-only verification — shape unchanged (explicit constraint)
- CSS/UI: none
- Env: conditional — if Phase 2 view-result-cache TTL or schema_version exposed as env var, update `contracts/env/env-contract.md`, `.env.example`, `env.schema.json`, and add env-default contract test
- Data shape: read-only verification — source columns unchanged (explicit non-goal)
- Business logic: review `contracts/business/business-rules.md` for any documented cache-strategy invariant
- CI/CD: none expected unless a new required check is introduced

## Required Tests
- unit: yes — canonical-key functions (granularity excluded), `ensure_dataset_loaded()` writes to canonical key, `try_compute_query_from_canonical_spool()` returns HIT after warmup
- contract: yes — API response shape unchanged; env-default contract test if TTL var added
- integration: yes — full warmup→query path: first query hits Oracle, subsequent filter/granularity switches resolve from canonical spool without Oracle
- E2E: yes (existing) — existing resource-history E2E tests must pass
- visual: no
- data-boundary: no
- resilience: yes — Redis-down and stale-parquet (schema_version mismatch) fallback to Oracle without `BinderException`
- fuzz/monkey: no
- stress: no (not pre-merge per governance)
- soak: no (not pre-merge per governance)

## Required Agents
1. `spec-architect` — write `design.md` BEFORE `implementation-planner`
2. `contract-reviewer` — confirm API/data-shape unchanged; verify env contract if new var introduced
3. `test-strategist` — write `test-plan.md`
4. `ci-cd-gatekeeper` — write `ci-gates.md`
5. `implementation-planner` — write `implementation-plan.md`
6. `backend-engineer` — implement the three-phase fix
7. `qa-reviewer` — release readiness

## Inferred Acceptance Criteria
- AC-1: After background warmup completes for a date range, `try_compute_query_from_canonical_spool()` returns a HIT (not SPOOL_MISS); request does not fall through to Oracle
- AC-2: `ensure_dataset_loaded()` writes the spool under the same canonical key that `try_compute_query_from_canonical_spool()` reads (key-hash parity verified by test)
- AC-3: Canonical cache key excludes `granularity`; two queries identical except for granularity (day/week/month/year) resolve against the same parquet without a new Oracle query
- AC-4: Switching filters (workcenter group / model) on a warm cache resolves from cache with no Oracle call; only first query for a new date range hits Oracle
- AC-5: API request/response shape for the resource-history endpoint is unchanged (route contract test passes)
- AC-6: Bumping `schema_version` invalidates old spool files; stale/incompatible parquet or Redis-down falls back to Oracle without `BinderException`/schema-mismatch; schema_version/parquet-cleanup documented in `ci-gates.md §Rollback Policy`
- AC-7: (Phase 2, if in scope) view-result cache keyed by canonical_key + granularity + filters returns cached `apply_view()` results within TTL and recomputes after expiry
- AC-8: Existing pytest, Vitest, and resource-history E2E suites pass; new tests cover BOTH canonical-spool path and Oracle fallback for every filter/granularity dimension

## Tasks Not Applicable
- not-applicable: 2.2, 3.4, 3.5, 4.2, 5.1, 5.2, 6.4

## Clarifications or Assumptions
- Assumption: no new public env var unless Phase 2 view-cache TTL is exposed; spec-architect to decide
- Open question (for spec-architect): (a) view-result cache TTL value; (b) whether System-A deprecation is in scope here or follow-up change
- Assumption: `schema_version` bump requires post-deploy parquet cleanup per CLAUDE.md spool runbook
- Assumption: multi-worker startup-lock pattern in `resource_history_duckdb_cache.py` must be preserved; spec-architect to confirm interaction with new warmup write path

## Context Manifest Draft

### Affected Surfaces
- resource-history caching (Redis spool key strategy + background warmup)
- shared spool/warmup infrastructure (read/verify only)

### Allowed Paths
- specs/changes/resource-history-cache-fix/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/services/resource_history_sql_runtime.py
- src/mes_dashboard/routes/resource_history_routes.py
- src/mes_dashboard/core/spool_warmup_scheduler.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/core/redis_df_store.py
- src/mes_dashboard/sql/resource_history/
- contracts/env/env-contract.md
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/CHANGELOG.md
- docs/cache-strategy.md
- docs/adr/
- tests/test_resource_cache.py
- tests/test_resource_cache_version_check.py
- tests/test_resource_dataset_cache.py
- tests/test_resource_history_duckdb_cache.py
- tests/test_resource_history_routes.py
- tests/test_resource_history_service.py
- tests/test_resource_history_sql_parity.py
- tests/test_resource_history_sql_runtime.py
- tests/integration/

### Agent Work Packets

#### spec-architect
- specs/changes/resource-history-cache-fix/
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/services/resource_history_sql_runtime.py
- src/mes_dashboard/routes/resource_history_routes.py
- src/mes_dashboard/core/spool_warmup_scheduler.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/core/redis_df_store.py
- docs/cache-strategy.md
- docs/adr/

#### contract-reviewer
- specs/changes/resource-history-cache-fix/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/CHANGELOG.md

#### test-strategist
- specs/changes/resource-history-cache-fix/
- tests/test_resource_cache.py
- tests/test_resource_cache_version_check.py
- tests/test_resource_dataset_cache.py
- tests/test_resource_history_duckdb_cache.py
- tests/test_resource_history_routes.py
- tests/test_resource_history_sql_runtime.py
- tests/integration/

#### ci-cd-gatekeeper
- specs/changes/resource-history-cache-fix/
- .github/workflows/

#### implementation-planner
- specs/changes/resource-history-cache-fix/
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/services/resource_history_sql_runtime.py
- src/mes_dashboard/routes/resource_history_routes.py

#### backend-engineer
- specs/changes/resource-history-cache-fix/
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/services/resource_history_sql_runtime.py
- src/mes_dashboard/routes/resource_history_routes.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/core/redis_df_store.py
- src/mes_dashboard/sql/resource_history/
- tests/test_resource_cache.py
- tests/test_resource_cache_version_check.py
- tests/test_resource_dataset_cache.py
- tests/test_resource_history_duckdb_cache.py
- tests/test_resource_history_routes.py
- tests/test_resource_history_sql_runtime.py
- tests/integration/
- contracts/env/env-contract.md
- contracts/CHANGELOG.md

#### qa-reviewer
- specs/changes/resource-history-cache-fix/
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/routes/resource_history_routes.py
- tests/integration/
