---
contract: ci
summary: CI gate inventory, artifact retention, and rollback requirements.
owner: platform-team
surface: delivery-pipeline
schema-version: 1.3.8
last-changed: 2026-05-13
breaking-change-policy: deprecate-2-minors
---

# CI/CD Gate Contract — MES Dashboard

> 來源：整合自 `ci/gate-policy.md`、`ci/required-check-policy.md`、`.github/workflows/contract-driven-gates.yml`（2026-05-05）

## Gate Inventory

| gate | tier | trigger | required | command | owner | artifact |
|---|---:|---|---:|---|---|---|
| contract-validate | 0 | local pre-PR | yes | `cdd-kit validate` | platform-team | — |
| lint | 0 | local / PR | yes | `ruff check .` | application-team | — |
| type-check | 0 | local / PR | informational | `mypy src/` | application-team | — |
| unit-mock-integration | 1 | PR | yes | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` | application-team | junit XML |
| frontend-unit | 1 | PR | yes | `cd frontend && npm run test` | application-team | vitest report |
| css-governance | 1 | PR | yes | `cd frontend && npm run css:check` | application-team | governance report |
| frontend-type-check | 1 | PR | informational | `cd frontend && npm run type-check` | application-team | — |
| playwright-resilience | 1 | PR | yes | `cd frontend && npx playwright test tests/playwright/resilience/` | application-team | playwright trace |
| playwright-data-boundary | 1 | PR | yes | `cd frontend && npx playwright test tests/playwright/data-boundary/` | application-team | playwright trace |
| playwright-critical-journeys | 1 | PR | yes | `cd frontend && npx playwright test tests/playwright/hold-overview.spec.js tests/playwright/reject-history.spec.js tests/playwright/query-tool.spec.js` | application-team | playwright trace |
| visual-regression | 2 | PR | informational | (TBD — Playwright screenshot diff) | application-team | screenshot diff |
| nightly-integration | 3 | weekly schedule / dispatch | yes (nightly) | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` | application-team | test report |
| stress-load | 4 | weekly schedule / dispatch | yes (weekly) | `pytest tests/stress/ -m "stress or load"` | platform-team | perf report |
| soak | 4 | weekly schedule / dispatch | yes (weekly) | `pytest tests/integration/test_soak_workload.py --run-integration-real -m "soak"` | platform-team | soak report |

## Gate Compatibility Notes

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

## Rollback Policy

- 任何 Tier 1 gate 變紅後 main branch 不得合入新 PR，直到修復。
- Tier 3/4 failure 需開 incident ticket，24 小時內回復或降級。
- Feature flag 是 rollback 第一防線；DB migration rollback 需附 down migration。

## Contract Change Policy

新增、移除或修改 CI gate 時，必須同步更新此契約（同一 PR），並在 PR 描述說明影響的 tier 和原因。

