# Change Classification

## Change Types
- primary: feature (filter promotion + cross-filter API)
- secondary: cache-schema-migration, sql-input-hardening, frontend-ux

## Risk Level
- high

## Impact Radius
- cross-module

## Tier
- 1

## Architecture Review Required
- yes
- reason: 4-tuple cross-filter cache layout (Option A live-SQL vs Option B in-memory filter on cached tuples vs Option C flat lists + filtered query) is an unresolved design decision in the change request; wildcard grammar and Oracle pattern translation also warrant architectural sign-off.

## Required Artifacts
Always required: change-request.md, change-classification.md, test-plan.md, ci-gates.md, tasks.yml

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | yes | Capture today's Type-only first-tier + 6-secondary flow, current `container_filter_cache` schema, and how `_build_extra_filters` composes today |
| proposal.md | yes | Tier 1 required |
| spec.md | no | design.md covers architecture; spec.md not needed for filter UX change |
| design.md | yes | Architecture review required (cache layout + wildcard grammar) |
| qa-report.md | yes | Tier 1 required at QA loop |
| regression-report.md | no | No prior bug to regress against |

## Required Contracts
- API: yes — new `GET /api/production-history/filter-options` (or extension) with `selected` param; main-query endpoint accepts `pj_packages[]`, `pj_bops[]`, `pj_functions[]`, `mfg_orders[]`, `lot_ids[]`, `wafer_lots[]` with `*` wildcard semantics
- CSS/UI: conditional — only if new layout classes are introduced beyond existing shared-ui MultiSelect/textarea
- Env: conditional — only if new env var introduced (e.g., `PRODUCTION_HISTORY_WILDCARD_MAX_PATTERNS`); decision deferred to spec-architect
- Data shape: yes — filter-options response shape (4 distinct lists conditioned on `selected`); cache payload schema version bump
- Business logic: yes — wildcard semantics (single `*` any position → `LIKE 'X%' / '%X' / '%X%'`); min prefix length; max patterns per field; deduplication; whitespace/comma/newline parsing
- CI/CD: yes — Cache rebuild rollback (Redis key version flip); fuzz gate; parquet cleanup if cache stored on disk

## Required Tests
- unit: yes — backend (`container_filter_cache` 4-tuple logic, wildcard parser/sanitizer, multi-line parser) + frontend (cross-filter loader, multi-line input parser)
- contract: yes — assert api / data-shape / business response shape and AC-N
- integration: yes — cross-filter chains (Package → BOP narrowing); cache hit/miss; lock contention; multi-worker against Oracle XE (nightly)
- E2E: yes — Playwright: select Package → BOP/Function options narrow; paste multi-line LOT IDs; wildcard `MA2025*`
- visual: yes — new filter rows layout; chip suppression on second-tier panel
- data-boundary: yes — empty cache; stale-schema cache poisoning; PJ_FUNCTION null/blank
- resilience: yes — Redis down → fall back to L1; cache lock holder dies mid-rebuild
- fuzz/monkey: yes (mandatory) — wildcard input: `'`, `;`, `--`, `/*`, `\x00`, unicode, 10KB strings, leading `*` only
- stress: yes (lightweight) — cache rebuild thundering herd; high-cardinality OR-IN list (1000 LOTs)
- soak: no — low risk of memory creep over 24h TTL window; can defer

## Required Agents

Tier 1 sequence (in execution order):

1. change-classifier (this run)
2. spec-architect — design the 4-tuple cross-filter cache layout, wildcard grammar, lock reuse plan
3. contract-reviewer — update api / data-shape / business / ci contracts (and css/env if needed)
4. test-strategist — author test-plan.md covering 11 test layers
5. backend-engineer — cache schema migration, service/_build_extra_filters, SQL EXTRA_FILTERS, filter-options endpoint
6. frontend-engineer — MultiSelect rows, multi-line textarea, cross-filter loader, second-tier chip suppression
7. dependency-security-reviewer — SQL injection audit of wildcard binder + Oracle parameter style
8. e2e-resilience-engineer — Playwright cross-filter + Redis/Oracle fault injection
9. monkey-test-engineer — wildcard fuzz (mandatory) + multi-line paste fuzz
10. ui-ux-reviewer — first-tier filter panel layout review
11. visual-reviewer — visual regression on new filter rows
12. ci-cd-gatekeeper — ci-gates.md with cache rollback + fuzz gate plan
13. qa-reviewer — assemble qa-report.md, run gate

## Inferred Acceptance Criteria

- AC-1: With all 4 low-cardinality filters empty, `GET /api/production-history/filter-options` returns the full distinct sets for `pj_types`, `pj_packages`, `pj_bops`, `pj_functions` from `container_filter_cache` (L1 or L2 hit) without an Oracle round-trip.
- AC-2: With `selected={"pj_packages":["X"]}`, the endpoint returns `pj_bops`, `pj_functions`, `pj_types` narrowed to values that co-occur with Package X in the cached 4-tuple set. Cross-filter is symmetric across all 4 fields.
- AC-3: The main-query endpoint applies the 4 MultiSelect filters and the 3 wildcard filters as `AND`-composed predicates; selecting nothing reproduces today's Type-only behavior (backward compatible).
- AC-4: Wildcard pattern `MA2025*` is translated to a parameter-bound Oracle `LIKE 'MA2025%'` (no string interpolation). Inputs containing `'`, `;`, `--`, `/*`, `*/`, control chars, or null bytes are rejected with a 400-class error and never reach Oracle. Pure `*` and patterns shorter than the configured minimum prefix are rejected.
- AC-5: Multi-line textarea input (newline-, comma-, or whitespace-separated) is parsed server-side into a deduplicated list; the parser is idempotent (`parse(parse(x)) == parse(x)`).
- AC-6: On simultaneous gunicorn worker startup, exactly one worker rebuilds `container_filter_cache` from Oracle while the rest poll a `.loading` sentinel and reuse the result (no Oracle thundering herd). Lock is released on success and on crash (timeout fallback ≤ 90 s).
- AC-7: The frontend filter panel renders 4 new MultiSelect rows + 3 new multi-line textareas in the first-tier section; the second-tier panel no longer offers `MFGORDERNAME`/`CONTAINERNAME`/`FIRSTNAME` chips (WorkCenter & Equipment remain second-tier).
- AC-8: Cache payload carries a schema-version field; on version mismatch, L2 entries are ignored and rebuilt rather than deserialized as the old shape.

## Tasks Not Applicable
- not-applicable:

## Clarifications or Assumptions

Open questions from change-request.md and proposed defaults (to confirm with spec-architect):

1. Cross-filter implementation strategy — Proposed default: **server-side in-memory filter over a cached 4-tuple list** (Option B). Rationale: keeps payload small, centralizes logic, avoids per-keystroke Oracle hits. Spec-architect to confirm vs Option A (live SQL each request) or Option C (cache flat + filtered query).
2. Function (PJ_FUNCTION) required vs optional — Default: **optional**, consistent with Package/BOP.
3. Wildcard grammar — Default: **single `*` at any position** (prefix `'X%'`, suffix `'%X'`, infix `'%X%'`). Multiple `*` rejected in v1. Min prefix length: **2 chars** before/after the `*`. Max patterns per field per request: **100**.
4. Second-tier filter retention after promotion — Default: **remove** `MFGORDERNAME`/`CONTAINERNAME`/`FIRSTNAME` from second-tier UI. **Keep** WorkCenter & Equipment in second-tier (still spool-derived).
5. Cache versioning — Embed `schema_version: 2` in cache payload; bump on layout change. L2 entries with mismatched version are dropped and rebuilt under lock.
6. Dependency on Change 2 — **Satisfied**: `prod-history-detail-raw-rows` archived 2026-05-14; spool now carries `PJ_FUNCTION`.
7. Oracle pattern hardening — Assumption: when wildcard expands to `LIKE '%X%'` (no anchor) on high-cardinality column, apply `ROWNUM <= N` cap (e.g., 100k) at the wildcard-LIKE subquery level, or require ≥ 4 chars before the wildcard. Spec-architect to choose.

## Context Manifest Draft

### Affected Surfaces

- production-history backend route (`routes/production_history_routes.py`)
- production-history service (`services/production_history_service.py`, `services/production_history_sql_runtime.py`)
- production-history SQL templates (`sql/production_history/`)
- `container_filter_cache` service + Redis L2 schema
- production-history frontend app (`frontend/src/production-history/`)
- shared-ui / shared-composables (MultiSelect, multi-line input parser reuse from `material-trace`)
- Contracts: api, data, business, css (conditional), env (conditional), ci

### Allowed Paths

- specs/changes/prod-history-first-tier-cache-filters/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/
- contracts/data/
- contracts/business/
- contracts/css/
- contracts/env/
- contracts/ci/
- src/mes_dashboard/routes/production_history_routes.py
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/services/production_history_job_service.py
- src/mes_dashboard/services/container_filter_cache.py
- src/mes_dashboard/services/resource_history_duckdb_cache.py
- src/mes_dashboard/services/filter_cache.py
- src/mes_dashboard/services/reason_filter_cache.py
- src/mes_dashboard/services/material_trace_service.py
- src/mes_dashboard/core/cache.py
- src/mes_dashboard/core/cache_plane.py
- src/mes_dashboard/core/redis_client.py
- src/mes_dashboard/core/request_validation.py
- src/mes_dashboard/core/response.py
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/sql/filters.py
- src/mes_dashboard/sql/builder.py
- src/mes_dashboard/sql/loader.py
- frontend/src/production-history/
- frontend/src/material-trace/
- frontend/src/shared-ui/components/
- frontend/src/shared-ui/index.ts
- frontend/src/shared-composables/
- frontend/src/core/api.ts
- frontend/src/core/endpoint-schemas.ts
- frontend/src/core/field-contracts.ts
- frontend/src/core/types.ts
- tests/test_production_history_service.py
- tests/test_production_history_routes.py
- tests/test_production_history_sql_runtime.py
- tests/test_container_filter_cache.py
- tests/test_common_filters.py
- tests/test_cache.py
- tests/test_cache_updater_lock_behavior.py
- tests/property/
- tests/routes/_fuzz_payloads.py
- tests/routes/test_fuzz_routes.py
- tests/integration/_multi_worker_harness.py
- tests/integration/test_multi_worker_concurrency.py
- tests/integration/test_real_multi_worker.py
- tests/integration/test_redis_chaos.py
- tests/integration/test_redis_timeout_fallback.py
- tests/stress/
- tests/e2e/
- frontend/tests/legacy/
- frontend/tests/validation/
- frontend/tests/abort/
- frontend/tests/playwright/
- shared/field_contracts.json
- data/table_schema_info.json

### Agent Work Packets

#### change-classifier
- specs/changes/prod-history-first-tier-cache-filters/
- specs/context/project-map.md
- specs/context/contracts-index.md

#### spec-architect
- specs/changes/prod-history-first-tier-cache-filters/
- src/mes_dashboard/services/container_filter_cache.py
- src/mes_dashboard/services/resource_history_duckdb_cache.py
- src/mes_dashboard/services/reason_filter_cache.py
- src/mes_dashboard/services/material_trace_service.py
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/core/cache.py
- src/mes_dashboard/core/cache_plane.py
- contracts/api/
- contracts/data/
- contracts/business/

#### contract-reviewer
- specs/changes/prod-history-first-tier-cache-filters/
- contracts/api/
- contracts/data/
- contracts/business/
- contracts/css/
- contracts/env/
- contracts/ci/
- shared/field_contracts.json

#### test-strategist
- specs/changes/prod-history-first-tier-cache-filters/
- contracts/api/
- contracts/data/
- contracts/business/
- tests/property/
- tests/routes/_fuzz_payloads.py
- tests/integration/_multi_worker_harness.py

#### backend-engineer
- specs/changes/prod-history-first-tier-cache-filters/
- src/mes_dashboard/routes/production_history_routes.py
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/services/production_history_job_service.py
- src/mes_dashboard/services/container_filter_cache.py
- src/mes_dashboard/services/filter_cache.py
- src/mes_dashboard/services/reason_filter_cache.py
- src/mes_dashboard/services/material_trace_service.py
- src/mes_dashboard/services/resource_history_duckdb_cache.py
- src/mes_dashboard/core/cache.py
- src/mes_dashboard/core/cache_plane.py
- src/mes_dashboard/core/redis_client.py
- src/mes_dashboard/core/request_validation.py
- src/mes_dashboard/core/response.py
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/sql/filters.py
- src/mes_dashboard/sql/builder.py
- src/mes_dashboard/sql/loader.py
- tests/test_production_history_service.py
- tests/test_production_history_routes.py
- tests/test_production_history_sql_runtime.py
- tests/test_container_filter_cache.py
- tests/test_common_filters.py
- tests/test_cache_updater_lock_behavior.py

#### frontend-engineer
- specs/changes/prod-history-first-tier-cache-filters/
- frontend/src/production-history/
- frontend/src/material-trace/
- frontend/src/shared-ui/components/
- frontend/src/shared-ui/index.ts
- frontend/src/shared-composables/
- frontend/src/core/api.ts
- frontend/src/core/endpoint-schemas.ts
- frontend/src/core/field-contracts.ts
- frontend/src/core/types.ts
- frontend/tests/legacy/
- frontend/tests/validation/
- frontend/tests/abort/

#### dependency-security-reviewer
- specs/changes/prod-history-first-tier-cache-filters/
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/sql/filters.py
- src/mes_dashboard/sql/builder.py
- src/mes_dashboard/core/request_validation.py
- contracts/api/
- contracts/business/

#### e2e-resilience-engineer
- specs/changes/prod-history-first-tier-cache-filters/
- tests/e2e/
- tests/integration/_multi_worker_harness.py
- tests/integration/test_multi_worker_concurrency.py
- tests/integration/test_real_multi_worker.py
- tests/integration/test_redis_chaos.py
- tests/integration/test_redis_timeout_fallback.py
- frontend/tests/playwright/

#### monkey-test-engineer
- specs/changes/prod-history-first-tier-cache-filters/
- tests/routes/_fuzz_payloads.py
- tests/routes/test_fuzz_routes.py
- tests/property/
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/core/request_validation.py
- contracts/business/

#### ui-ux-reviewer
- specs/changes/prod-history-first-tier-cache-filters/
- frontend/src/production-history/
- frontend/src/shared-ui/components/
- contracts/css/

#### visual-reviewer
- specs/changes/prod-history-first-tier-cache-filters/
- frontend/src/production-history/
- frontend/tests/playwright/

#### ci-cd-gatekeeper
- specs/changes/prod-history-first-tier-cache-filters/
- contracts/ci/
- .github/workflows/

#### qa-reviewer
- specs/changes/prod-history-first-tier-cache-filters/
- contracts/
- tests/
- frontend/tests/
