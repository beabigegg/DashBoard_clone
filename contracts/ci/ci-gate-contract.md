---
contract: ci
summary: CI gate inventory, artifact retention, and rollback requirements.
owner: platform-team
surface: delivery-pipeline
schema-version: 1.3.31
last-changed: 2026-06-19
breaking-change-policy: deprecate-2-minors
---

# CI/CD Gate Contract — MES Dashboard

> 來源：整合自 `ci/gate-policy.md`、`ci/required-check-policy.md`、`.github/workflows/contract-driven-gates.yml`（2026-05-05）

## Gate Inventory

| gate | tier | trigger | required | command | owner | artifact |
|---|---:|---|---:|---|---|---|
| contract-validate | 0 | local pre-PR | yes | `cdd-kit validate` | platform-team | — |
| response-shape-validate | 1 | push / PR | yes | `cdd-kit validate --contracts` | platform-team | — |
| lint | 0 | local / PR | yes | `ruff check .` | application-team | — |
| type-check | 0 | local / PR | informational | `mypy src/` | application-team | — |
| unit-mock-integration | 1 | PR | yes | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` | application-team | junit XML |
| frontend-unit | 1 | PR | yes | `cd frontend && npm run test` | application-team | vitest report |
| css-governance | 1 | PR | yes | `cd frontend && npm run css:check` | application-team | governance report |
| frontend-type-check | 1 | PR | informational | `cd frontend && npm run type-check` | application-team | — |
| playwright-resilience | 1 | PR | yes | `cd frontend && npx playwright test tests/playwright/resilience/` | application-team | playwright trace |
| playwright-data-boundary | 1 | PR | yes | `cd frontend && npx playwright test tests/playwright/data-boundary/` | application-team | playwright trace |
| playwright-critical-journeys | 1 | PR | yes | `cd frontend && npx playwright test tests/playwright/hold-overview.spec.js tests/playwright/reject-history.spec.js tests/playwright/query-tool.spec.js tests/playwright/eap-alarm.spec.js` | application-team | playwright trace |
| visual-regression | 2 | PR | informational | (TBD — Playwright screenshot diff) | application-team | screenshot diff |
| nightly-integration | 3 | weekly schedule / dispatch | yes (nightly) | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` | application-team | test report |
| stress-load | 4 | weekly schedule / dispatch | yes (weekly) | `pytest tests/stress/ -m "stress or load"` | platform-team | perf report |
| soak | 4 | weekly schedule / dispatch | yes (weekly) | `pytest tests/integration/test_soak_workload.py --run-integration-real -m "soak"` | platform-team | soak report |

## Gate Compatibility Notes

### RQ prewarm unification + spool TTL alignment (unify-duckdb-prewarm-rq)

- **Tier 1 unit assertions** (covered by existing `unit-mock-integration` gate):
  - `_WARMUP_JOBS` contains the downtime_analysis DuckDB prewarm entry (AC-3).
  - `resource_dataset_cache._CACHE_TTL` resolves to 72000 (20h); `CACHE_TTL_DATASET` remains 7200 (2h) (AC-4).
  - `downtime_analysis_cache._CACHE_TTL` resolves to 72000; `CACHE_TTL_DATASET` unchanged (AC-4).
  - `RESOURCE_HISTORY_SPOOL_TTL` and `DOWNTIME_ANALYSIS_CACHE_TTL` documented defaults match `env-contract.md` (env-contract pin test pattern).
- **Tier 3 multi-worker integration updates** (covered by existing `nightly-integration` gate): `tests/integration/test_preload_fork_safety.py` updated to assert: (1) no daemon-thread `start_duckdb_prewarm()` call on gunicorn startup for either service; (2) both services' prewarm RQ jobs appear in `_WARMUP_JOBS` and are enqueued; (3) Oracle prewarm call count is exactly 1 across N workers.
- **No new gate tier or command**: all new tests fall within existing `unit-mock-integration` (Tier 1) and `nightly-integration` (Tier 3) gate commands.
- **Deploy note**: operators must be aware that the implicit spool TTL for resource_history and downtime_analysis changes from 2h to 20h on deploy. No operator action required; the new defaults are intentional. Update ops monitoring for cache-freshness if tracking spool age.
- **Schema-version bump to 1.3.19 (patch)**: additive gate-compatibility note only; gate tier, command, and status are unchanged.

### preload_app fork-safety coverage (gunicorn-preload-workers)

New Tier 3 multi-worker integration test (`tests/integration/test_preload_fork_safety.py`, markers: `integration_real` + `multi_worker`) asserts the following invariants after enabling `preload_app = True`:

1. Each single-run prewarm task (downtime_analysis, material_consumption, resource_history DuckDB, resource_cache `init_cache()`) executes exactly once per gunicorn restart across N workers — Oracle call count is 1, not N.
2. Each worker holds independent (non-inherited) DB engine pool, Redis pool, and SQLite handles after `post_fork` reinit — no OS file descriptor is shared across worker PIDs.
3. No "timed out waiting for peer worker" log line appears (resource_history_duckdb_cache lock deadlock is resolved).
4. No orphan background thread exists in the master process after fork.

Covered by existing `nightly-integration` gate command (`pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x`) — no gate tier, command, or status change. Schema-version bump to 1.3.18 (patch — additive gate-compatibility note only).

### frontend-type-check scope expansion (Phase 1a — migrate-core-to-typescript)

- **Before Phase 1a**: `tsconfig.json` `include` was `["src/core/"]` targeting only the `index.ts` barrel placeholder. The gate ran 0 substantive `.ts` modules through strict-mode checking.
- **From Phase 1a onward**: `include` is `["src/core/**/*"]`, covering all 21 core `.ts` modules under `strict: true`. The gate's effective coverage increased substantially in the same PR that performed the `.js` → `.ts` rename.
- **Status unchanged**: the gate remains **informational** (continue-on-error: true). Promotion to required follows the standard Informational Gate Promotion Policy.
- **No schema-version bump**: this is a coverage expansion, not a contract interface change.

### frontend-type-check scope expansion (Phase 1b — migrate-shared-composables-ts)

- **Before Phase 1b**: `tsconfig.json` `include` was `["src/core/**/*"]`, covering 21 core `.ts` modules.
- **From Phase 1b onward**: `include` is `["src/core/**/*", "src/shared-composables/**/*"]`, additionally covering all 11 shared-composable `.ts` modules under `strict: true`.
- **Status unchanged**: the gate remains **informational** (continue-on-error: true). Promotion to required follows the standard Informational Gate Promotion Policy.
- **Schema-version bump to 1.3.1 (patch)**: additive prose only — gate tier, command, and status are unchanged. Matching Phase 1a precedent at ci 1.2.1.

### frontend-type-check scope expansion (Phase 1d — migrate-admin-shared-ts)

- **Before Phase 1d**: `tsconfig.json` `include` was `["src/core/**/*", "src/shared-composables/**/*", "src/shared-ui/**/*"]`, covering 54 modules across the three previously migrated scopes.
- **From Phase 1d onward**: `include` is `["src/core/**/*", "src/shared-composables/**/*", "src/shared-ui/**/*", "src/admin-shared/**/*"]`, additionally covering the 5 modules in `admin-shared/` (4 Vue SFCs + 1 composable) under `strict: true`.
- **Status unchanged**: the gate remains **informational** (continue-on-error: true). Promotion to required follows the standard Informational Gate Promotion Policy.
- **Schema-version bump to 1.3.2 (patch)**: additive prose only — gate tier, command, and status are unchanged. Matching Phase 1b precedent at ci 1.3.1.

### frontend-type-check scope expansion (Phase 1e — migrate-resource-shared-ts)

- **Before Phase 1e**: `tsconfig.json` `include` was `["src/core/**/*", "src/shared-composables/**/*", "src/shared-ui/**/*", "src/admin-shared/**/*"]`, covering 59 modules across the four previously migrated scopes.
- **From Phase 1e onward**: `include` is `["src/core/**/*", "src/shared-composables/**/*", "src/shared-ui/**/*", "src/admin-shared/**/*", "src/resource-shared/**/*"]`, additionally covering the 3 modules in `resource-shared/` (2 Vue SFCs + 1 constants module) under `strict: true`.
- **Status unchanged**: the gate remains **informational** (continue-on-error: true). Promotion to required follows the standard Informational Gate Promotion Policy.
- **Schema-version bump to 1.3.3 (patch)**: additive prose only — gate tier, command, and status are unchanged. Matching Phase 1d precedent at ci 1.3.2.

### frontend-type-check scope expansion (Phase 1f — migrate-wip-shared-ts)

- **Before Phase 1f**: `tsconfig.json` `include` was `["src/core/**/*", "src/shared-composables/**/*", "src/shared-ui/**/*", "src/admin-shared/**/*", "src/resource-shared/**/*"]`, covering 62 modules across the five previously migrated scopes.
- **From Phase 1f onward**: `include` is `["src/core/**/*", "src/shared-composables/**/*", "src/shared-ui/**/*", "src/admin-shared/**/*", "src/resource-shared/**/*", "src/wip-shared/**/*"]`, additionally covering the 6 modules in `wip-shared/` (3 Vue SFCs + 2 composables + 1 constants module) under `strict: true`. This phase also removes `@ts-expect-error` suppressions from `shared-composables/` and `shared-ui/` that were placed as explicit cross-phase placeholders.
- **Status unchanged**: the gate remains **informational** (continue-on-error: true). Promotion to required follows the standard Informational Gate Promotion Policy.
- **Schema-version bump to 1.3.4 (patch)**: additive prose only — gate tier, command, and status are unchanged. Matching Phase 1e precedent at ci 1.3.3.

### frontend-type-check scope expansion (Phase 3 — migrate-reject-history-ts)

- **Before Phase 3**: `tsconfig.json` `include` covered `core/`, `shared-composables/`, `shared-ui/`, `admin-shared/`, `resource-shared/`, `wip-shared/`.
- **From Phase 3 onward**: `include` gains `"src/reject-history/**/*"`, covering `App.vue`, `main.ts`, `useRejectHistoryDuckDB.ts`, and 6 component SFCs (`DetailTable.vue`, `FilterPanel.vue`, `ParetoGrid.vue`, `ParetoSection.vue`, `SummaryCards.vue`, `TrendChart.vue`) under `strict: true`.
- **Gate tier unchanged**: informational (continue-on-error: true). Promotion follows the standard Informational Gate Promotion Policy.
- **Schema-version bump to 1.3.5 (patch)**: additive prose only — gate tier, command, and status are unchanged. Matching Phase 1f precedent at ci 1.3.4.

### frontend-type-check scope expansion (Phase 3 — migrate-hold-history-ts)

- **Before this change**: `tsconfig.json` `include` covered `core/`, `shared-composables/`, `shared-ui/`, `admin-shared/`, `resource-shared/`, `wip-shared/`, `reject-history/`.
- **From this change onward**: `include` gains `"src/hold-history/**/*"`, covering all `.ts`/`.vue` files migrated from `hold-history/` under `strict: true`.
- **Gate tier unchanged**: informational (continue-on-error: true). Promotion follows the standard Informational Gate Promotion Policy.
- **Schema-version bump to 1.3.6 (patch)**: additive prose only — gate tier, command, and status are unchanged.

### frontend-type-check scope expansion (Phase 3 — migrate-wip-hold-ts)

- **Before this change**: `tsconfig.json` `include` covered `core/`, `shared-composables/`, `shared-ui/`, `admin-shared/`, `resource-shared/`, `wip-shared/`, `reject-history/`, `hold-history/`.
- **From this change onward**: `include` gains `"src/wip-overview/**/*"`, `"src/wip-detail/**/*"`, `"src/hold-overview/**/*"`, `"src/hold-detail/**/*"`, covering all `.ts`/`.vue` files migrated from the four feature apps under `strict: true`.
- **Gate tier unchanged**: informational (continue-on-error: true). Promotion follows the standard Informational Gate Promotion Policy.
- **Schema-version bump to 1.3.7 (patch)**: additive prose only — gate tier, command, and status are unchanged.

### frontend-type-check scope expansion (Phase 3 — migrate-qc-gate-ts)

- **Before this change**: `tsconfig.json` `include` covered `core/`, `shared-composables/`, `shared-ui/`, `admin-shared/`, `resource-shared/`, `wip-shared/`, `reject-history/`, `hold-history/`, `wip-overview/`, `wip-detail/`, `hold-overview/`, `hold-detail/`, `resource-status/`.
- **From this change onward**: `include` gains `"src/qc-gate/**/*"`, covering all `.ts`/`.vue` files migrated from `qc-gate/` (`main.ts`, `App.vue`, `composables/useQcGateData.ts`, `components/LotTable.vue`, `components/QcGateChart.vue`) under `strict: true`.
- **Gate tier unchanged**: informational (continue-on-error: true). Promotion follows the standard Informational Gate Promotion Policy.
- **Schema-version bump to 1.3.8 (patch)**: additive prose only — gate tier, command, and status are unchanged.

### frontend-type-check scope expansion (Phase 3 item #15 — migrate-resource-history-ts)

- **Before this change**: `tsconfig.json` `include` covered `core/`, `shared-composables/`, `shared-ui/`, `admin-shared/`, `resource-shared/`, `wip-shared/`, `reject-history/`, `hold-history/`, `wip-overview/`, `wip-detail/`, `hold-overview/`, `hold-detail/`, `resource-status/`, `qc-gate/`.
- **From this change onward**: `include` gains `"src/resource-history/**/*"`, covering all `.ts`/`.vue` files migrated from `resource-history/` (`main.ts`, `useResourceHistoryDuckDB.ts`, `App.vue`, `components/FilterBar.vue`, `components/KpiCards.vue`, `components/TrendChart.vue`, `components/StackedChart.vue`, `components/ComparisonChart.vue`, `components/HeatmapChart.vue`, `components/DetailSection.vue`) under `strict: true`.
- **Gate tier unchanged**: informational (continue-on-error: true). Promotion follows the standard Informational Gate Promotion Policy.
- **Schema-version bump to 1.3.9 (patch)**: additive prose only — gate tier, command, and status are unchanged.

### frontend-type-check scope expansion (Phase 3 — migrate-job-query-ts)

- **Before this change**: `tsconfig.json` `include` covered `core/`, `shared-composables/`, `shared-ui/`, `admin-shared/`, `resource-shared/`, `wip-shared/`, `reject-history/`, `hold-history/`, `wip-overview/`, `wip-detail/`, `hold-overview/`, `hold-detail/`, `resource-status/`, `qc-gate/`, `resource-history/`.
- **From this change onward**: `include` gains `"src/job-query/**/*"`, covering all `.ts`/`.vue` files migrated from `job-query/` (`main.ts`, `App.vue`, `composables/useJobQueryData.ts`) under `strict: true`.
- **Gate tier unchanged**: informational (continue-on-error: true). Promotion follows the standard Informational Gate Promotion Policy.
- **Schema-version bump to 1.3.11 (patch)**: additive prose only — gate tier, command, and status are unchanged.

### New test coverage — resource-history-perf

- **New Tier 3 nightly integration test**: `tests/integration/test_resource_history_prewarm.py` — startup pre-warm + Redis key assertion (requires real Oracle + Redis; `integration_real` marker). Covered by existing `nightly-integration` gate command; no gate tier or command change.
- **Tier 4 stress extension**: `tests/stress/test_resource_history_stress.py` extended with concurrent progress-endpoint poll test (N=50 concurrent pollers; `stress` marker). Covered by existing `stress-load` gate command; no gate tier or command change.
- **Tier 1 Playwright extensions**: new `playwright/resilience/` and `playwright/data-boundary/` specs for progress endpoint (503 mid-poll resilience; malformed progress response boundary). Covered by existing `playwright-resilience` and `playwright-data-boundary` gates; no gate tier or command change.
- **Schema-version bump to 1.3.10 (patch)**: additive prose documenting new test coverage scope under existing gates; gate tier, command, and status are unchanged.
- **Source**: change `resource-history-perf`.

### New fuzz + cache rollback coverage — prod-history-first-tier-cache-filters

- **Tier 1 fuzz scope expansion**: `tests/routes/test_fuzz_routes.py` extended to fuzz the new `mfg_orders[]` / `lot_ids[]` / `wafer_lots[]` wildcard fields on `POST /api/production-history/query`. Malicious payloads (`'`, `;`, `--`, `/*`, `*/`, `\x00`, control chars, multi-`*`, pure `*`, 10 KB strings, 1000-pattern overflow) MUST resolve to `VALIDATION_ERROR` (400) and never reach Oracle (business-rules.md PHF-02, PHF-03, PHF-06). Covered by existing `unit-mock-integration` and route-fuzz gates; no gate tier or command change.
- **Tier 1 contract assertion**: `GET /api/production-history/filter-options` response shape (`pj_types`/`packages`/`bops`/`pj_functions` arrays + `meta.schema_version: 2`) asserted under `unit-mock-integration` gate via `tests/test_production_history_routes.py`. No gate tier or command change.
- **Tier 3 multi-worker coverage**: `tests/integration/test_multi_worker_concurrency.py` extended to assert `container_filter_cache` rebuild lock behavior (only one worker hits Oracle on simultaneous cold start; losers reuse via Redis L2 within 90 s; business-rules.md PHF-05). Covered by existing `nightly-integration` gate; `integration_real` marker.
- **Rollback (cache schema_version)**: This change introduces a new rollback primitive — bumping `container_filter_cache` payload `schema_version` from `2` → `3` in a follow-up deploy invalidates all L2 entries on the next read (PHF-04). This avoids `redis-cli DEL` post-deploy. The runbook step for rollback is: (1) bump `schema_version` in `container_filter_cache.py`, (2) deploy, (3) optionally `rm tmp/container_filter_cache.loading` if stale sentinel is suspected. No parquet cleanup required (cache is Redis-only, not on-disk parquet).
- **Schema-version bump to 1.3.12 (patch)**: additive prose only — gate tier, command, and status are unchanged.
- **Source**: change `prod-history-first-tier-cache-filters`.

### frontend-type-check scope expansion (Phase 3 — migrate-material-trace-ts)

- **Before this change**: `tsconfig.json` `include` covered `core/`, `shared-composables/`, `shared-ui/`, `admin-shared/`, `resource-shared/`, `wip-shared/`, `reject-history/`, `hold-history/`, `wip-overview/`, `wip-detail/`, `hold-overview/`, `hold-detail/`, `resource-status/`, `qc-gate/`, `resource-history/`, `job-query/`, `production-history/`, `query-tool/`.
- **From this change onward**: `include` gains `"src/material-trace/**/*"`, covering `main.ts` and `App.vue` under `strict: true`.
- **Gate tier unchanged**: informational (continue-on-error: true). Promotion follows the standard Informational Gate Promotion Policy.
- **Schema-version bump to 1.3.13 (patch)**: additive prose only — gate tier, command, and status are unchanged.
- **Source**: change `migrate-material-trace-ts`.

### frontend-type-check scope expansion + frontend-build addition (admin-pages-vue-spa + admin-dashboard-ts-entry)

- **Before**: `tsconfig.json` `include` covered `core/` through `mid-section-defect/`. Vite build input did not include `admin-pages`.
- **From this change**: `include` gains `"src/admin-dashboard/**/*"` and `"src/admin-pages/**/*"`. Vite `rollupOptions.input` gains `admin-pages: src/admin-pages/index.html`, producing `dist/admin-pages.{html,js,css}`.
- Gate tier unchanged: informational (continue-on-error: true).
- Source: change `admin-pages-vue-spa-and-admin-dashboard-ts-entry`.

### frontend-build scope change (remove-unused-pages)

- **Removed from Vite build input**: `tables`, `admin-performance`, `admin-user-usage-kpi` — all three app directories deleted; no longer built.
- **Added to Vite build input**: `production-history` — HTML entry added to `rollupOptions.input`.
- **Net effect**: `dist/` will no longer contain `tables.*`, `admin-performance.*`, `admin-user-usage-kpi.*` bundles; `production-history.*` bundle now present.
- **Schema-version bump to 1.3.15 (patch)**: documents build-scope change only — gate tier, command, and status are unchanged.
- **Source**: change `remove-unused-pages`.

### frontend-type-check scope expansion (Phase 3 — migrate-mid-section-defect-ts)

- **Before this change**: `tsconfig.json` `include` covered `core/`, `shared-composables/`, `shared-ui/`, `admin-shared/`, `resource-shared/`, `wip-shared/`, `reject-history/`, `hold-history/`, `wip-overview/`, `wip-detail/`, `hold-overview/`, `hold-detail/`, `resource-status/`, `qc-gate/`, `resource-history/`, `job-query/`, `production-history/`, `query-tool/`, `material-trace/`.
- **From this change onward**: `include` gains `"src/mid-section-defect/**/*"`, covering `main.ts` and `App.vue` (with `<script setup lang="ts">`) under `strict: true`.
- **Gate tier unchanged**: informational (continue-on-error: true). Promotion follows the standard Informational Gate Promotion Policy.
- **Schema-version bump to 1.3.14 (patch)**: additive prose only — gate tier, command, and status are unchanged.
- **Source**: change `migrate-mid-section-defect-ts`.

## Required Check Policy

- **Tier 1** gates（unit-tests、frontend-unit、css-governance、critical-e2e）block merge。
- **Tier 2** gates（visual-regression、real-infra-smoke）run on PR but do not block until stable (20 days / 60 runs / pass rate > threshold / runtime within limit)。
- **Tier 3** nightly gates：failure must be triaged within 1 business day。
- **Tier 4** weekly soak：failure triggers production-readiness review。

新增 gate 必須先以 informational 啟動，達 promotion criteria 後才提升為 required。

## Gate Tier Semantics

| tier | name | when blocked |
|---|---|---|
| 0 | Local Fast Gate | 本地 pre-PR；lint、typecheck、targeted unit、contract validate |
| 1 | PR Required Gate | blocks merge；build、unit、API/CSS/env/data contracts、critical E2E、fuzz |
| 2 | PR Informational Gate | runs on PR, does not block；visual regression、real-infra smoke |
| 3 | Nightly Real-Infra Gate | real DB/cache/queue；driver timeout、failover、race condition |
| 4 | Weekly Soak / Stress Gate | long-run stability；soak hours、load vus |

## Workflow Configuration

檔案：`.github/workflows/contract-driven-gates.yml`、`.github/workflows/frontend-tests.yml`、`.github/workflows/backend-tests.yml`

| job | trigger | stack | status |
|---|---|---|---|
| `contract-and-fast-tests` | push / PR | Python 3.11 + Node 22 + conda mes-dashboard | configured |
| `e2e-critical` | PR only | Node 22 + conda + Playwright chromium | configured |
| `nightly-integration` | weekly schedule / dispatch | conda mes-dashboard | configured |
| `scheduled-stress-soak` | weekly schedule / dispatch | conda mes-dashboard | configured |
| `frontend-unit-tests` | push / PR | Node 22 + vue-tsc | configured |
| `unit-and-integration-tests` | push / PR | Python 3.13 + Node 22 | configured |

**Node version constraint**: All jobs that run pytest (including `unit-and-integration-tests` in `backend-tests.yml`) MUST include `uses: actions/setup-node@v4 / node-version: "22"`. `tests/test_frontend_*_parity.py` call Node subprocesses with `--experimental-strip-types`, which requires Node ≥22.6. Dropping this step causes all parity tests to fail with exit code 9.

### Environment Constraints (conda)

- `environment.yml` MUST pin `nodejs>=22.6` (not `>=22`). Conda may resolve `>=22` to 22.0–22.5, which lack `--experimental-strip-types`. In CI, pytest runs in `shell: bash -el {0}` (conda-activated login shell), making conda's node take precedence over `setup-node@v4`'s node. A loose pin silently breaks all parity tests.
  Evidence: `environment.yml:16`; CI fix commit `b2fd91b`.

**Test markers（pytest.ini）：**
- `integration` — mock DB（pre-merge OK）
- `e2e` / `local_e2e` — 需要 running server 或 in-process Flask
- `integration_real` — 需 `--run-integration-real` + real Oracle/Redis（Tier 3）
- `stress` / `load` — concurrent load（Tier 4）
- `soak` / `multi_worker` — 需 `--run-integration-real`（Tier 4）
- `property` — Hypothesis property tests（Tier 1，pre-merge OK）

**Test directories：**

| directory | marker | tier | pre-merge |
|---|---|---:|---:|
| `tests/` (root) | none / integration | 1 | yes |
| `tests/routes/` | none | 1 | yes |
| `tests/property/` | property | 1 | yes |
| `tests/e2e/` | e2e / local_e2e | 1 | local_e2e only |
| `tests/integration/` | integration_real | 3 | no |
| `tests/stress/` | stress / load | 4 | no |
| `tests/manual/` | — | manual | no |
| `frontend/tests/` (Vitest) | — | 1 | yes |
| `frontend/tests/playwright/resilience/` | — | 1 | yes |
| `frontend/tests/playwright/data-boundary/` | — | 1 | yes |
| `frontend/tests/playwright/*.spec.js` | — | 1 | yes |

## Informational Gate Promotion Policy

Promote from informational to required after ALL of:
- 20 calendar days or 60 runs
- pass rate above agreed threshold
- failures triaged and documented
- runtime within acceptable limit
- owner assigned

## Artifact Retention Policy

| artifact | retention |
|---|---|
| pytest / vitest report | 30 days |
| Playwright traces | 7 days (longer on failure) |
| Screenshot diffs | 30 days |
| Soak/stress reports | 90 days |

## material-part-consumption Worker Queue & Deploy Gates

**New RQ worker queue `material-consumption`**: dedicated queue for detail async jobs (business-rules.md MC-04). Isolated from other report queues. `rq_monitor_service._QUEUE_NAMES` must include `os.getenv("MATERIAL_CONSUMPTION_WORKER_QUEUE", "material-consumption")`.

**Deploy checklist** (verify before serving traffic):
1. Enable + start the `material-consumption` worker systemd unit and watchdog.
2. Verify Admin Dashboard `/admin/api/worker/status` shows `material-consumption` queue with ≥ 1 worker.
3. Verify `docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json` includes `/material-consumption` → dist asset. Missing entry crashes gunicorn via `_validate_in_scope_asset_readiness()`.
4. Verify `docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json` classifies `/material-consumption` as in-scope.
5. Verify `data/page_status.json` includes `/material-consumption` page object in drawer-2.

**Rollback checklist** (complete before gunicorn restart):
1. Remove `/material-consumption` entry from `asset_readiness_manifest.json` BEFORE restart — stale entry with no dist asset crashes gunicorn.
2. Remove `/material-consumption` entry from `data/page_status.json` — stale entry emits "缺少 route contract: /material-consumption" in sidebar.
3. Run `rm -f tmp/query_spool/material_consumption/*.parquet` — spool files become orphaned after rollback (parquet schema is breaking-change surface per data-shape-contract.md §3.9).
4. Disable + stop the `material-consumption` worker systemd unit and watchdog.

**Parquet schema gate**: any PR that renames, adds, or removes a column in the `material_consumption_service.py` spool write path MUST add `rm -f tmp/query_spool/material_consumption/*.parquet` to both deploy and rollback runbooks and update `data-shape-contract.md §3.9`.

**No parquet cleanup in query-tool**: this gate entry is specific to `material_consumption`. Do NOT add `rm tmp/query_spool/material_consumption/*.parquet` to query-tool rollbacks (query-tool has no persistent spool).

---

## downtime-browser-duckdb Gate Compatibility Note

**New Playwright spec → CI browser install step required** (`frontend-tests.yml`): `npx playwright install --with-deps chromium` must be added before `npx playwright test tests/playwright/downtime-analysis.spec.ts` per CLAUDE.md CI Workflow Notes. Without this step, CI runners exit with "Executable doesn't exist."

**Concurrency** (`downtime-playwright-e2e` job):
```yaml
concurrency:
  group: ${{ github.ref }}-downtime-e2e
  cancel-in-progress: true
```

**Artifact retention**: playwright trace for new spec: `retention-days: 7` (30 on failure); stress/soak report: `retention-days: 90`.

**New gates added** (all Tier 1 for this change):
- `downtime-playwright-e2e`: `cd frontend && npx playwright test tests/playwright/downtime-analysis.spec.ts`
- `playwright-resilience`: extended with atomicity + error-banner specs
- `playwright-data-boundary`: extended with malformed-parquet + cross-midnight specs
- `frontend-unit`: extended with `useDowntimeDuckDB.test.ts` (7 parity tests + taxonomy + CSV)

**Parity regression gate** (`nightly-parity-regression`, Tier 3, required from day one):
- `pytest tests/integration/test_downtime_parity_regression.py --run-integration-real`
- Python `_merge_cross_shift_events` / `_bridge_jobid` vs browser DuckDB SQL on 184k-row fixture; cross-midnight event + ambiguous-tie cases required.

**OOM-risk note (flag-OFF rollback)**: Rolling back to `DOWNTIME_BROWSER_DUCKDB=false` without reinstating `_MAX_ORACLE_DAYS` accepts gunicorn worker OOM risk on >90-day Oracle-path queries under the 6 GB/no-swap host profile. Flag-off must only be used for short rollback windows (< 24h). If the rollback window exceeds 24h, re-introduce the 90-day guard or migrate to a host with more RAM.

**Parquet cleanup (schema-breaking rollback)**: If raw-spool schema shipped and must be abandoned, run:
```bash
rm -f tmp/query_spool/downtime_analysis_base_events/*.parquet
rm -f tmp/query_spool/downtime_analysis_job_bridge/*.parquet
```
Bumping `SCHEMA_VERSION` in `downtime_analysis_cache.py` also orphans live raw parquets by key (design.md D4) without a manual `rm`.

**Enriched spool retention**: `downtime_analysis_events` namespace parquets do not need cleanup on cutover — they expire naturally via 20h TTL (DA-07).

## downtime-rq-async Gate Compatibility Note

**New Playwright spec → CI browser install step required** (`frontend-tests.yml`): add `npx playwright install --with-deps chromium` before `npx playwright test tests/playwright/downtime-analysis.spec.js` per CLAUDE.md CI Workflow Notes. Without this step, CI runners exit with "Executable doesn't exist."

**Tier 1 unit assertions** (covered by existing `unit-mock-integration` gate):
- Threshold branch logic: date range ≥ `DOWNTIME_ASYNC_DAY_THRESHOLD` → 202; < threshold → 200 (AC-1, AC-2).
- Env-var default pinning: `DOWNTIME_ASYNC_ENABLED=True`, `DOWNTIME_ASYNC_DAY_THRESHOLD=30`, `DOWNTIME_WORKER_QUEUE="downtime-query"`, `DOWNTIME_JOB_TIMEOUT_SECONDS=1800` (`monkeypatch.setattr`, not `setenv` — module-level constants).
- `register_job_type()` registration: use `importlib.reload()` after clearing the registry dict to re-run registration side-effects.
- Pct milestone sequence assertion: 5→15→60→90→100 (ASYNC-DA-01, data-shape-contract.md §3.14.3).
- DA-11 atomicity: `execute_downtime_query_job()` writes both parquets or neither (resilience).

**Tier 1 Playwright coverage** (covered by existing `playwright-resilience` gate):
- `tests/e2e/test_downtime_analysis_e2e.py`: long-range query → 202 → polling → progress bar → results; cancel mid-job; short-range → 200 sync unaffected.

**Tier 3 integration coverage** (covered by existing `nightly-integration` gate):
- `tests/integration/test_downtime_rq_async.py`: `enqueue_job_dynamic()` dispatch; spool write ordering; DA-11 atomicity validation; parity test (RQ worker fn vs sync path produce byte/row-identical spools, AC-3).

**Deploy checklist** (verify before serving traffic):
1. Enable + start the `downtime-query` worker systemd unit and watchdog.
2. Verify Admin Dashboard `/admin/api/worker/status` shows `downtime-query` queue with ≥ 1 worker.
3. `rq_monitor_service._QUEUE_NAMES` must include `os.getenv("DOWNTIME_WORKER_QUEUE", "downtime-query")`.
4. `DOWNTIME_ASYNC_ENABLED` defaults to `true`; no explicit env set required unless disabling.

**Rollback checklist** (zero-downtime path: set flag=false):
1. Set `DOWNTIME_ASYNC_ENABLED=false` in environment; reload gunicorn (no restart required).
2. All downtime queries fall back to synchronous path; no parquet spool cleanup required.
3. Hard rollback (remove worker): stop the `downtime-query` RQ worker systemd unit. In-flight jobs time out at `DOWNTIME_JOB_TIMEOUT_SECONDS` (default 1800 s); frontend retries on next query.

**Parquet schema gate**: `downtime_analysis_base_events` and `downtime_analysis_job_bridge` namespaces are shared with `downtime-browser-duckdb`; schema-breaking changes require `rm -f tmp/query_spool/downtime_analysis_base_events/*.parquet tmp/query_spool/downtime_analysis_job_bridge/*.parquet` (same cleanup as downtime-browser-duckdb).

**No new gate tier or command**: all new tests fall within existing `unit-mock-integration` (Tier 1), `playwright-resilience` (Tier 1), and `nightly-integration` (Tier 3) gate commands.

**Schema-version bump to 1.3.21 (patch)**: additive gate-compatibility note only; gate tier, command, and status are unchanged.

## hold-history-rq-async Gate Compatibility Note

**Tier 1 unit assertions** (covered by existing `unit-mock-integration` gate):
- Threshold branch: date range ≥ `HOLD_ASYNC_DAY_THRESHOLD` → 202; < threshold → 200 (AC-1, AC-2).
- Env-var default pinning: `HOLD_ASYNC_ENABLED=True`, `HOLD_ASYNC_DAY_THRESHOLD=90`, `HOLD_WORKER_QUEUE="hold-history-query"`, `HOLD_JOB_TIMEOUT_SECONDS=1800` (`monkeypatch.setattr`, not `setenv` — module-level constants).
- `register_job_type()` registration: use `importlib.reload()` after clearing the registry dict to re-run registration side-effects.
- Pct milestone: coarse bracket 5→15→90→100 bracketing the `execute_primary_query()` call (per implementation-plan.md Known Risks, coarse option chosen; ADR-0003 row-count chunking exclusion does NOT apply to hold-history).
- Worker fn wraps `execute_primary_query()` without mutation (AC-3).

**Tier 1 Playwright coverage** (covered by existing `playwright-resilience` gate):
- `frontend/tests/playwright/hold-history-flat-table.spec.js`: long-range query → 202 → polling → progress bar → results; short-range → 200 sync unaffected.

**Tier 3 integration coverage** (covered by existing `nightly-integration` gate):
- `tests/integration/test_hold_history_rq_async.py`: `enqueue_job_dynamic()` dispatch; parity test — worker fn vs sync path produce identical result for same query (AC-3).

**Deploy checklist** (verify before serving traffic):
1. Start the `hold-history-query` RQ worker systemd unit.
2. Verify Admin Dashboard shows `hold-history-query` queue with ≥ 1 worker.
3. `rq_monitor_service._QUEUE_NAMES` must include `os.getenv("HOLD_WORKER_QUEUE", "hold-history-query")`.
4. `HOLD_ASYNC_ENABLED` defaults to `true`; no explicit env set required unless disabling.

**Rollback checklist** (zero-downtime):
1. Set `HOLD_ASYNC_ENABLED=false`; reload gunicorn (`kill -HUP`). All queries fall back to sync; no spool cleanup needed.
2. Hard rollback: stop the `hold-history-query` worker systemd unit. In-flight jobs time out at `HOLD_JOB_TIMEOUT_SECONDS`; frontend retries on next query (sync fallback via `is_async_available()` returning False).

**No new gate tier or command**: all new tests fall within existing `unit-mock-integration` (Tier 1), `playwright-resilience` (Tier 1), and `nightly-integration` (Tier 3) gate commands.

**Schema-version bump to 1.3.22 (patch)**: additive gate-compatibility note only; no gate tier, command, or status changed.

## resource-history-rq-async Gate Compatibility Note

**Tier 1 unit assertions** (covered by existing `unit-mock-integration` gate):
- Threshold branch: date range ≥ `RESOURCE_ASYNC_DAY_THRESHOLD` → 202; < threshold → 200 (AC-1, AC-2).
- Env-var default pinning: `RESOURCE_ASYNC_ENABLED=True`, `RESOURCE_ASYNC_DAY_THRESHOLD=90`, `RESOURCE_WORKER_QUEUE="resource-history-query"`, `RESOURCE_JOB_TIMEOUT_SECONDS=1800` (`monkeypatch.setattr`, not `setenv` — module-level constants).
- `register_job_type()` registration: use `importlib.reload()` after clearing the registry dict to re-run registration side-effects.
- Pct milestone: coarse bracket 5→15→90→100 bracketing the `execute_primary_query()` call (per implementation-plan.md Known Risks, coarse option chosen; ADR-0003 row-count chunking exclusion does NOT apply to resource-history).
- Worker fn wraps `execute_primary_query()` without mutation (AC-3).
- `owner` is inside `_params` dict forwarded to worker (AC-7).

**Tier 1 Playwright coverage** (covered by existing `playwright-resilience` gate):
- `frontend/tests/playwright/resource-history-async.spec.ts`: long-range query → 202 → polling → progress bar → results; short-range → 200 sync unaffected.

**Tier 3 integration coverage** (covered by existing `nightly-integration` gate):
- `tests/integration/test_resource_history_rq_async.py`: `enqueue_job_dynamic()` dispatch; parity test — worker fn vs sync path produce identical result for same query (AC-3).

**Deploy checklist** (verify before serving traffic):
1. Start the `resource-history-query` RQ worker systemd unit.
2. Verify Admin Dashboard shows `resource-history-query` queue with ≥ 1 worker.
3. `rq_monitor_service._QUEUE_NAMES` must include `os.getenv("RESOURCE_WORKER_QUEUE", "resource-history-query")`.
4. `RESOURCE_ASYNC_ENABLED` defaults to `true`; no explicit env set required unless disabling.

**Rollback checklist** (zero-downtime):
1. Set `RESOURCE_ASYNC_ENABLED=false`; reload gunicorn (`kill -HUP`). All queries fall back to sync; no spool cleanup needed.
2. Hard rollback: stop the `resource-history-query` worker systemd unit. In-flight jobs time out at `RESOURCE_JOB_TIMEOUT_SECONDS`; frontend retries on next query (sync fallback via `is_async_available()` returning False).

**No new gate tier or command**: all new tests fall within existing `unit-mock-integration` (Tier 1), `playwright-resilience` (Tier 1), and `nightly-integration` (Tier 3) gate commands.

**Schema-version bump to 1.3.23 (patch)**: additive gate-compatibility note only; no gate tier, command, or status changed.


### eap-alarm-analysis deploy/rollback checklist

**Deploy checklist** (eap-alarm-analysis):
1. Set env vars: `EAP_ALARM_WORKER_QUEUE`, `EAP_ALARM_JOB_TIMEOUT_SECONDS`, `EAP_ALARM_SPOOL_TTL`, `EAP_ALARM_SPOOL_DIR` (defaults in env-contract.md §Async Worker — EAP ALARM Spool).
2. Start `mes-dashboard-eap-alarm-worker.service` systemd unit before deploying gunicorn.
3. Verify `eap_alarm` in `spool_routes._ALLOWED_NAMESPACES` (checked by Tier 1 `unit-mock-integration` gate).
4. Verify `tests/integration/test_spool_routes.py` parametrize covers `eap_alarm` (Tier 1).
5. Playwright spec `tests/playwright/eap-alarm.spec.js` added to `playwright-critical-journeys` gate command.

**Rollback checklist** (eap-alarm-analysis):
1. Stop `mes-dashboard-eap-alarm-worker.service`. In-flight spool jobs are abandoned; 410 `CACHE_EXPIRED` is returned to the frontend (graceful).
2. Hard rollback: `rm -f tmp/query_spool/eap_alarm/*.parquet`; restart gunicorn. Schema changes require parquet cleanup (per EA-06).
3. No flag-off path: EAP ALARM spool is always-async (no sync fallback). Removing the routes module is the cleanest rollback.
4. Nav update (portal-shell) is purely additive; no rollback needed unless the nav entry conflicts with a future "EAP" category owner.

**No new gate tier or command**: all new tests fall within existing `unit-mock-integration` (Tier 1), `playwright-critical-journeys` (Tier 1), `playwright-resilience` (Tier 1), and `nightly-integration` (Tier 3) gate commands.

**Schema-version bump to 1.3.25 (patch)**: additive deploy/rollback checklist + playwright gate spec addition. No gate tier, command, or status changed.

### eap-alarm-unified-job-poc gate compatibility note

`eap-alarm-unified-job-poc` (P1 migration) adds new test files (`test_base_chunked_duckdb_job.py` extensions, `test_eap_alarm_service.py` extensions, `test_async_query_job_service.py` extensions, integration tests in `tests/integration/`, stress/soak in `tests/stress/`) and one new contract test (`tests/contract/test_env_eap_alarm_flag.py`). All new files fall within existing gate commands:
- `backend-tests.yml` unit-and-integration-tests already discovers `tests/` root and `tests/integration/` (new tests added automatically).
- `stress-tests.yml` already runs `tests/stress/ -m stress --run-stress` (new `test_async_job_stress.py` eap_alarm cases picked up).
- `soak-tests.yml` already runs `tests/integration/test_soak_workload.py` (no new command needed).
- `e2e-tests.yml` already runs `tests/e2e/ -m e2e` (new `test_eap_alarm_e2e.py` cases picked up).

**No new gate tier, command, or workflow file required.** Feature flag `EAP_ALARM_USE_UNIFIED_JOB=off` default means zero behavioral change for all gate runs until flag is explicitly set to `on`.

**Schema-version bump to 1.3.26 (patch)**: additive gate-compatibility note for P1 migration. No gate tier, command, or status changed.

## downtime-duckdb-join-migration Gate Compatibility Note

**P5 migration — new `DowntimeJob(BaseChunkedDuckDBJob)` + feature flag (default `off`):**

- New `DowntimeJob` class added in `src/mes_dashboard/workers/downtime_worker.py` (job type `downtime_unified`). Covered by existing `unit-mock-integration` gate (`tests/test_base_chunked_duckdb_job.py` extensions, `tests/test_query_cost_policy.py` `_APPROVED_CALLERS` stem addition — auto-discovered).
- New contract test: `tests/contract/test_env_downtime_flag.py` (AC-6 env-contract pin for `DOWNTIME_USE_UNIFIED_JOB` default `off`) — auto-discovered by `unit-mock-integration` gate.
- New integration tests: `tests/integration/test_downtime_rq_async.py`, `tests/integration/test_rowcount_flag_parity.py` — skipped pre-merge (`integration_real` marker); covered by existing `nightly-integration` gate.
- New stress test: `tests/stress/test_downtime_analysis_stress.py` — covered by existing `stress-load` gate (`tests/stress/ -m "stress or load"`).
- New E2E test: `tests/e2e/test_downtime_analysis_e2e.py` — covered by existing `e2e-tests.yml` (`tests/e2e/ -m e2e`); starts informational.
- Feature flag `DOWNTIME_USE_UNIFIED_JOB=off` (default) ensures zero behavioral change under all gate runs until explicitly set.
- Reuses existing `downtime-query` RQ queue and `mes-dashboard-downtime-query-worker.service` — no new systemd unit, no new workflow file, no gate tier change. Additive; no existing gates changed.
- `chunk_strategy=RESOURCEID` (per-RESOURCEID group) with `requires_cross_chunk_reduction=True`; `ROW_COUNT` and `TIME` chunking explicitly prohibited (ADR-0003).
- `stress-soak-report.md` authored by stress-soak-engineer required before flag promotion to `on` in production (not before merge).

**Deploy checklist:**
1. No new worker service required — reuses existing `mes-dashboard-downtime-query-worker.service` and `downtime-query` queue.
2. Verify `downtime-query` queue and worker remain healthy after deploy.
3. Confirm `DOWNTIME_USE_UNIFIED_JOB` reads as `off` in ALL processes (gunicorn + worker) before promoting to `on`. Flag is a module-level constant frozen at boot; `kill -HUP` alone is insufficient.
4. Worker env-var parity: `mes-dashboard-downtime-query-worker.service` MUST export `DOWNTIME_USE_UNIFIED_JOB` with the same value as gunicorn.
5. Run `tests/test_base_chunked_duckdb_job.py`, `tests/test_query_cost_policy.py`, and `tests/contract/test_env_downtime_flag.py` green before promoting flag.
6. Obtain sign-off on `stress-soak-report.md` (DuckDB on-disk spill under 184k-row fixture, no Python heap OOM) before promoting flag to `on` in production.

**Rollback checklist:**
1. Set `DOWNTIME_USE_UNIFIED_JOB=off`.
2. **Restart** gunicorn and the `downtime-query` worker — env vars are module-level constants frozen at boot; `kill -HUP` is insufficient.
3. No spool cleanup required: `DowntimeJob` writes to the existing `downtime_analysis_base_events` and `downtime_analysis_job_bridge` namespaces; spool schema is unchanged between unified-job and legacy paths.
4. Hard rollback (revert PR): in-flight `DowntimeJob` tasks are abandoned; frontend receives HTTP 410 (`CACHE_EXPIRED`) and retries gracefully on next user query.
5. Schema-breaking spool rollback only (if `_SCHEMA_VERSION` was bumped): `rm -f tmp/query_spool/downtime_analysis_base_events/*.parquet tmp/query_spool/downtime_analysis_job_bridge/*.parquet`.

**No new gate tier or command**: all new tests fall within existing `unit-mock-integration` (Tier 1), `nightly-integration` (Tier 3), `stress-load` (Tier 4), and `e2e-tests.yml` (informational Tier 1) gate commands.

**Schema-version bump to 1.3.30 (patch)**: gate-compatibility note added; no gate tier, command, or status changed.

## Rollback Policy

- 任何 Tier 1 gate 變紅後 main branch 不得合入新 PR，直到修復。
- Tier 3/4 failure 需開 incident ticket，24 小時內回復或降級。
- Feature flag 是 rollback 第一防線；DB migration rollback 需附 down migration。

## Contract Change Policy

新增、移除或修改 CI gate 時，必須同步更新此契約（同一 PR），並在 PR 描述說明影響的 tier 和原因。

## response-shape-adr0007 Gate Compatibility Note

**New Tier 1 required gate — `response-shape-validate`** (`contract-and-fast-tests` job):

- Step `Response-shape contract gate` added to `.github/workflows/contract-driven-gates.yml`
  immediately after the existing `OpenAPI sync gate` step.
- Command: `cdd-kit validate --contracts`
- What it checks: for every entry in `tests/contract/response-samples.json`, loads the
  captured sample from `tests/contract/samples/*.json` (with optional `dataPath` envelope
  unwrap), and validates the payload against the typed schema declared under `## Schemas`
  in `contracts/api/api-contract.md` (resolved via `contracts/openapi.json`). Endpoints
  without a typed schema cell are skipped. A mismatch is exit 1 (blocking).
- Local pre-PR equivalent: `cdd-kit validate --contracts` (Tier 0).
- No production source (`src/`) is modified by this gate.
- Rollback: revert schema or sample file in a fix PR; no service restart required.

**Schema-version bump to 1.3.24 (patch)**: new required Tier 1 gate added; no existing
gate tier, command, or status changed.

## production-reject-history-migration Gate Compatibility Note

**P2 migration — two new worker modules, two feature flags (default `off`):**

- Two new job modules: `src/mes_dashboard/workers/production_history_worker.py` (job type `production_history_unified`) and `src/mes_dashboard/workers/reject_history_worker.py` (job type `reject_unified`). Both covered by existing `unit-mock-integration` gate (`pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=...`).
- Two new test files: `tests/test_production_history_unified_job.py`, `tests/test_reject_history_unified_job.py` — auto-discovered by existing gate commands.
- Two new integration test files: `tests/integration/test_production_history_rq_async.py`, `tests/integration/test_reject_history_rq_async.py` — skipped pre-merge (nightly gate).
- Feature flags `PRODUCTION_HISTORY_USE_UNIFIED_JOB=off` and `REJECT_HISTORY_USE_UNIFIED_JOB=off` (default) ensure zero behavioral change under all gate runs until explicitly set.
- New systemd unit `deploy/mes-dashboard-production-history-worker.service` (additive; existing units unchanged).
- No new workflow file. No gate tier change. Additive; no existing gates changed.

**Deploy checklist:**
1. Start `mes-dashboard-production-history-worker.service` on all nodes after deploy.
2. Verify `production-history-query` queue appears in Admin Dashboard → Worker Status (or `rq_monitor_service._QUEUE_NAMES`).
3. Confirm both flags read as `off` in ALL processes (gunicorn + workers) before promoting either to `on`. Flags are module-level constants — env-var drift between processes silently routes different paths.
4. Worker env-var parity: `mes-dashboard-production-history-worker.service` MUST export `PRODUCTION_HISTORY_USE_UNIFIED_JOB`; `mes-dashboard-reject-worker.service` MUST export `REJECT_HISTORY_USE_UNIFIED_JOB`.

**Rollback checklist:**
1. Set `PRODUCTION_HISTORY_USE_UNIFIED_JOB=off` and/or `REJECT_HISTORY_USE_UNIFIED_JOB=off`.
2. **Restart** gunicorn and the respective worker(s) — env vars are module-level constants frozen at boot; `kill -HUP` is insufficient (reloads workers but not master environment).
3. No spool cleanup required: spool schema is unchanged between unified-job and legacy paths.
4. If rolling back the new `mes-dashboard-production-history-worker.service`: stop and disable it before restarting gunicorn.

**Schema-version bump to 1.3.27 (patch)**: gate-compatibility note added; no gate tier, command, or status changed.

## resource-history-migration Gate Compatibility Note

**P3 migration — two new worker modules, one feature flag (default `off`):**

- Two new job modules: `src/mes_dashboard/workers/resource_history_base_worker.py` (job type `resource-history-base`, `always_async=True`, `requires_cross_chunk_reduction=False`) and `src/mes_dashboard/workers/resource_history_oee_worker.py` (job type `resource-history-oee`, `always_async=True`, `requires_cross_chunk_reduction=True`). Both covered by existing `unit-mock-integration` gate.
- New test files: `tests/test_resource_history_unified_job.py`, `tests/test_resource_history_job_service.py` — auto-discovered by existing gate commands.
- Integration stub: `tests/integration/test_resource_history_rq_async.py` — skipped pre-merge (nightly gate, `integration_real` marker).
- Feature flag `RESOURCE_HISTORY_USE_UNIFIED_JOB=off` (default) ensures zero behavioral change under all gate runs until explicitly set.
- Reuses existing `resource-history-query` RQ queue and `mes-dashboard-resource-history-worker.service` — no new systemd unit, no new workflow file, no gate tier change. Additive; no existing gates changed.

**Deploy checklist:**
1. No new worker service required — reuses existing `mes-dashboard-resource-history-worker.service`.
2. Verify `resource-history-query` queue and worker remain healthy after deploy.
3. Confirm `RESOURCE_HISTORY_USE_UNIFIED_JOB` reads as `off` in ALL processes (gunicorn + worker) before promoting to `on`. Flag is a module-level constant frozen at boot.
4. Worker env-var parity: `mes-dashboard-resource-history-worker.service` MUST export `RESOURCE_HISTORY_USE_UNIFIED_JOB` with the same value as gunicorn.
5. Run `tests/test_resource_history_unified_job.py` and `tests/test_query_cost_policy.py` green before promoting flag.

**Rollback checklist:**
1. Set `RESOURCE_HISTORY_USE_UNIFIED_JOB=off`.
2. **Restart** gunicorn and the resource-history worker — env vars are module-level constants frozen at boot.
3. No spool cleanup required: spool schema is unchanged between unified-job and legacy paths.

**Schema-version bump to 1.3.28 (patch)**: gate-compatibility note added; no gate tier, command, or status changed.

## material-trace-streaming-migration Gate Compatibility Note

**P4 migration — new job class + entry function + feature flag (default `off`):**

- New `MaterialTraceJob` class added to `src/mes_dashboard/services/material_trace_duckdb_runtime.py` (inline, no new file). Covered by new test `tests/test_material_trace_unified_job.py` — auto-discovered by existing `unit-mock-integration` gate command.
- New entry function `execute_material_trace_unified_job` added to `src/mes_dashboard/services/material_trace_service.py` + `register_job_type("material-trace-unified")`. Covered by same test file.
- No new worker service required — reuses existing `mes-dashboard-trace-worker.service` and `trace-events` RQ queue.
- No new workflow file, no new gate tier. Additive; no existing gates changed.
- Feature flag `MATERIAL_TRACE_USE_UNIFIED_JOB=off` (default) ensures zero behavioral change under all gate runs until explicitly set.
- New test files: `tests/test_material_trace_unified_job.py`, `tests/contract/test_env_material_trace_flag.py` — auto-discovered by existing gate commands.

**Deploy checklist:**
1. No new worker service required — reuses existing `mes-dashboard-trace-worker.service`.
2. Verify `trace-events` queue and worker remain healthy after deploy.
3. Confirm `MATERIAL_TRACE_USE_UNIFIED_JOB` reads as `off` in ALL processes (gunicorn + worker) before promoting to `on`. Flag is a module-level constant frozen at boot.
4. Worker env-var parity: `mes-dashboard-trace-worker.service` MUST export `MATERIAL_TRACE_USE_UNIFIED_JOB` with the same value as gunicorn.
5. Run `tests/test_material_trace_unified_job.py` green before promoting flag.

**Rollback checklist:**
1. Set `MATERIAL_TRACE_USE_UNIFIED_JOB=off`.
2. **Restart** gunicorn and the trace worker — env vars are module-level constants frozen at boot.
3. No spool cleanup required: spool namespace `material_trace` and parquet schema are unchanged between unified-job and legacy paths.

**Schema-version bump to 1.3.29 (patch)**: gate-compatibility note added; no gate tier, command, or status changed.

## query-path-c-elimination-cleanup Gate Compatibility Note

**P4+P5 Path-C elimination — new `query-tool` RQ job type + env-var removal:**

- **No new workflow files required.** All new tests (`tests/contract/test_env_query_tool_flag.py`, `tests/integration/test_query_tool_rq_async.py`, `tests/stress/test_query_tool_stress.py`) fall within existing gate discovery scopes.
- **Tier 1 `unit-mock-integration` gate** auto-discovers: new env-pin contract tests (4 removed vars absent + `QUERY_TOOL_USE_RQ` present with default off), `tests/test_job_registry.py` count update (10→11, "query-tool" in expected_types set), `tests/test_batch_query_engine.py` DeprecationWarning assertion, `tests/test_query_cost_policy.py` `_DEPRECATED_THRESHOLD_VARS` removal, query_tool/wip dispatch unit tests (mock `is_async_available=True` + `enqueue_query_job` per CLAUDE.md async-gated route unit test pattern — CI has no Redis).
- **Tier 1 `response-shape-validate` gate** (`cdd-kit validate --contracts`) validates the new 202+job_id async-dispatch shape for `query_tool_routes` under `QUERY_TOOL_USE_RQ=on`.
- **Tier 3 `nightly-integration` gate** picks up `tests/integration/test_query_tool_rq_async.py` (`integration_real` marker) on the first nightly run after merge — verifies flag-on/off parity and worker-blocking-elimination (AC-1/AC-2/AC-8).
- **Tier 4 `stress-load` gate** picks up `tests/stress/test_query_tool_stress.py` (`stress` marker) on the next weekly run — verifies RQ Oracle concurrency bounded by `HEAVY_QUERY_MAX_CONCURRENT` semaphore and no gunicorn worker starvation (AC-8). `stress-soak-report.md` required before promoting `QUERY_TOOL_USE_RQ` to `on` in production.
- **CI env-var removal**: the 4 `*_ASYNC_DAY_THRESHOLD` vars are not set in any existing `env:` block in `backend-tests.yml` or `contract-driven-gates.yml`; no workflow YAML edit required for their removal.
- **Feature flag `QUERY_TOOL_USE_RQ=off` (default)**: CI workflows do not need to set this explicitly. All gate runs exercise the flag-off (default / safe) path.
- **No spool/parquet cleanup**: `query_tool_routes` has no persistent spool; do not add parquet cleanup to rollback steps for this change (see §material-part-consumption for contrast).
- **Same-PR constraints enforced at Tier 1**: IP-2 (job registry count) + IP-7 (env removal) must co-ship with IP-11 (test updates) and IP-9/IP-10 (contract+example env updates) in the same PR or the `unit-mock-integration` and `response-shape-validate` gates will fail.

**Schema-version bump to 1.3.31 (patch)**: additive gate-compatibility note for P4+P5 Path-C elimination. No gate tier, command, or status changed.

## CHANGELOG

## [ci 1.3.31] — 2026-06-19
- query-path-c-elimination-cleanup: Gate-compatibility note for P4+P5 Path-C elimination — new `query-tool` RQ job type (test_job_registry count 10→11), 4 `*_ASYNC_DAY_THRESHOLD` vars removed (no workflow YAML env-block edit required), `QUERY_TOOL_USE_RQ=off` default means zero behavioral change until explicitly set, `stress-soak-report.md` required before flag promotion. All new tests auto-discovered by existing gate commands. No new workflow file or gate tier. Additive; no existing gates changed.

## [ci 1.3.30] — 2026-06-19
- downtime-duckdb-join-migration: Gate-compatibility note for P5 migration — `DowntimeJob(BaseChunkedDuckDBJob)` + `execute_downtime_unified_job`; reuses `downtime-query` queue and existing worker service; `chunk_strategy=RESOURCEID` with `requires_cross_chunk_reduction=True` (ADR-0003 compliance). Feature flag `DOWNTIME_USE_UNIFIED_JOB=off` (default) means zero behavioral change until explicitly set. `stress-soak-report.md` required before flag promotion. No new workflow file or gate tier. Additive; no existing gates changed.

## [ci 1.3.29] — 2026-06-19
- material-trace-streaming-migration: Gate-compatibility note for P4 migration — `MaterialTraceJob` + `execute_material_trace_unified_job` in existing service/runtime files; reuses `trace-events` queue and existing worker service; no new workflow file or gate tier. Feature flag `MATERIAL_TRACE_USE_UNIFIED_JOB=off` (default) means zero behavioral change until explicitly set. Additive; no existing gates changed.

## [ci 1.3.28] — 2026-06-19
- resource-history-migration: Gate-compatibility note for P3 migration — two new worker modules (`resource_history_base_worker`, `resource_history_oee_worker`) reuse existing `resource-history-query` queue and worker service; no new workflow file or gate tier needed. Feature flag `RESOURCE_HISTORY_USE_UNIFIED_JOB=off` (default) means zero behavioral change until explicitly set. Additive; no existing gates changed.

## [ci 1.3.27] — 2026-06-19
- production-reject-history-migration: Gate-compatibility note for P2 migration (two new worker modules, feature flags default `off`, new systemd unit, two new integration test files skipped pre-merge). Additive; no existing gates changed.

## [ci 1.3.25] — 2026-06-18
- eap-alarm-analysis: Added deploy/rollback checklist for EAP ALARM worker (`EAP_ALARM_*` env vars, `mes-dashboard-eap-alarm-worker.service`, parquet cleanup). Added `tests/playwright/eap-alarm.spec.js` to `playwright-critical-journeys` gate. Added compatibility note (no new gate tier; all tests within existing Tier 1/3 commands). Additive; no existing gates changed.

## [ci 1.3.24]
- response-shape-adr0007 (2026-06-15): Added `response-shape-validate` as a new required Tier 1 gate (`cdd-kit validate --contracts`) wired into `contract-driven-gates.yml`. Validates 158 API endpoint response samples against declared schemas.

## [ci 1.3.17]
- material-part-consumption (2026-05-20): Added worker queue deploy/rollback checklist for the new `material-consumption` RQ worker. No existing gates changed.

