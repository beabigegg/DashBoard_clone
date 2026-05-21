# CI/CD Gate Plan

## Change ID

resource-status-package-group

## Required Gates

| gate | tier | required | trigger | command / workflow | artifact |
|---|---:|:---:|---|---|---|
| contract-validate | 0 | yes | local pre-PR | `cdd-kit validate` | — |
| lint | 0 | yes | local / PR | `ruff check .` | — |
| backend-unit | 1 | yes | pull_request | `pytest tests/test_resource_cache.py tests/test_resource_service.py tests/test_resource_routes.py -x --tb=short` via `backend-tests / unit-and-integration-tests` | junit XML |
| frontend-unit | 1 | yes | pull_request | `cd frontend && npm run test` via `frontend-tests / frontend-unit-tests` | vitest report |
| css-governance | 1 | yes | pull_request | `cd frontend && npm run css:check` via `frontend-tests / frontend-unit-tests` | governance report |
| type-check | 2 | informational | pull_request | `cd frontend && npm run type-check` via `frontend-tests / frontend-unit-tests` | — |
| contract-tests | 1 | yes | pull_request | `pytest tests/test_api_contract.py tests/test_resource_routes.py::test_resource_status_options_returns_package_groups_field -x --tb=short` via `backend-tests / unit-and-integration-tests` | junit XML |

**Gates not applicable to this change:**

| gate | reason |
|---|---|
| e2e-critical | No new critical user journey; additive fields on existing page. No new Playwright spec required. |
| data-boundary (Playwright) | No new spool or parquet surface; 91% NULL passthrough verified by unit fixture. |
| resilience (Playwright) | No new async job path or network-failure surface. |
| nightly-integration (Tier 3) | No new real-Oracle path; lookup dict uses in-process dict with 7-day TTL — no new `integration_real`-marked tests. |
| stress / soak (Tier 4) | 46-row in-process dict; no new load surface. |
| manual dispatch (Tier 5) | Not required. |

## CI/CD Workflow

No new workflow files are introduced. All gates run under existing workflows:

- **`.github/workflows/backend-tests.yml`** — `unit-and-integration-tests` job covers `pytest tests/test_resource_cache.py tests/test_resource_service.py tests/test_resource_routes.py` and contract tests. Path trigger already includes `src/mes_dashboard/services/**` and `src/mes_dashboard/routes/**`, so this workflow fires automatically on PR.
- **`.github/workflows/frontend-tests.yml`** — `frontend-unit-tests` job covers `npm run test`, `npm run css:check`, and `npm run type-check`. Path trigger already includes `frontend/src/**`, so this workflow fires automatically on PR.
- **`.github/workflows/contract-driven-gates.yml`** — `contract-and-fast-tests` job runs `cdd-kit validate` on every PR.

No workflow file edits are required.

### Required status checks (branch protection)

The following job names must be listed in branch protection required status checks (they already are for this project; no change needed):

- `unit-and-integration-tests` (backend-tests.yml)
- `frontend-unit-tests` (frontend-tests.yml)
- `contract-and-fast-tests` (contract-driven-gates.yml)

`type-check` runs inside `frontend-unit-tests` with `continue-on-error: true` — it is informational and must not be promoted to required as part of this change.

## Promotion Policy

- **type-check** (Tier 2, informational): promote to required after 20 calendar days / 60 runs with pass rate above threshold and runtime within limit, following the standard Informational Gate Promotion Policy in `contracts/ci/ci-gate-contract.md`. This change does not alter that timeline.
- No new gates are introduced that require a promotion schedule.

## Rollback Policy

1. **Feature is additive-only** — rolling back means reverting the PR. No DB migration, no new Redis key, no new parquet spool; no post-rollback cleanup steps are required.
2. **Package-group lookup dict (in-process, 7-day TTL)** — populated from `DW_MES_RESOURCE_PACKAGEGROUP` at first gunicorn startup after deploy. If Oracle is unavailable at startup, all records will carry `PACKAGEGROUPNAME: null` until the next TTL refresh (7 days or gunicorn restart). This is acceptable degraded behavior; the frontend hides the row when `PACKAGEGROUPNAME` is null.
3. **No parquet cleanup required** — resource-status uses no parquet spool (unlike production-history or resource-history). Do not add `rm tmp/query_spool/resource_status/*.parquet` to any rollback runbook for this change.
4. **No `asset_readiness_manifest.json` / `route_scope_matrix.json` / `data/page_status.json` edits** — this change modifies an existing page (`/portal-shell/resource`) without adding or removing a route. No manifest entries are created, so no manifest cleanup is needed on rollback.
5. **Gate regression during rollback**: if the reverted PR causes a Tier 1 gate to fail on `main`, no new PR may merge until the gate is green again (per `contracts/ci/ci-gate-contract.md` §Rollback Policy).

## Artifact Retention

Follows project defaults in `contracts/ci/ci-gate-contract.md §Artifact Retention Policy`:

| artifact | retention |
|---|---|
| pytest / vitest report | 30 days |
| Playwright traces | 7 days (longer on failure) |

No new artifact types are introduced.

## Merge Eligibility Decision

**Mergeable** when all Tier 1 required gates are green:

- `unit-and-integration-tests` passes (backend unit + contract tests including test-plan.md rows: resource_cache lookup dict TTL, CHAR key consistency, PACKAGEGROUPNAME NULL passthrough, filter-options `package_groups`, route per-kwarg forwarding, warm-cache/snapshot path filter assertion).
- `frontend-unit-tests` passes (vitest + css:check).
- `contract-and-fast-tests` passes (`cdd-kit validate`).

The informational `type-check` step may be yellow without blocking merge.
